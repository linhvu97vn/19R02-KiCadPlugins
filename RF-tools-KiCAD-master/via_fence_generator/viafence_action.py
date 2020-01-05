#!/usr/bin/env python

# Implementation of the action plugin derived from pcbnew.ActionPlugin
import pcbnew
import os
import sys
import re
import time
import json
import math
import wx

from collections import OrderedDict
from .viafence import *
from .viafence_dialogs import *

debug = False

def wxLogDebug(msg,show):
    """printing messages only if show is omitted or True"""
    if show:
        wx.LogMessage(msg)
# 
def getTrackAngleRadians(track):
    #return math.degrees(math.atan2((p1.y-p2.y),(p1.x-p2.x)))
    return (math.atan2((track.GetEnd().y - track.GetStart().y), (track.GetEnd().x - track.GetStart().x)))
#

def distance (p1,p2):
    return math.hypot(p1.y-p2.y,p1.x-p2.x)

class ViaFenceAction(pcbnew.ActionPlugin):
    # ActionPlugin descriptive information
    def defaults(self):
        self.name = "Via Fence Generator\nversion 2.1"
        self.category = "Modify PCB"
        self.description = "Add a via fence to nets or tracks on the board"
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "resources/fencing-vias.png")
        self.show_toolbar_button = True

    def dumpJSON(self, file):
        dict = {
            'pathList': self.pathList, 
            'viaOffset': self.viaOffset, 
            'viaPitch': self.viaPitch, 
            'viaPoints': self.viaPoints if hasattr(self, 'viaPoints') else []
        }
        with open(file, 'w') as file:
            json.dump(dict, file, indent=4, sort_keys=True)

    # Return an ordered {layerId: layerName} dict of enabled layers
    def getLayerMap(self):
        layerMap = []
        for i in list(range(pcbnew.PCB_LAYER_ID_COUNT)):
            if self.boardObj.IsLayerEnabled(i):
                layerMap += [[i, self.boardObj.GetLayerName(i)]]
        return OrderedDict(layerMap)

    # Return an ordered {netCode: netName} dict of nets in the board
    def getNetMap(self):
        netMap = OrderedDict(self.boardObj.GetNetsByNetcode())
        netMap.pop(0) # TODO: What is Net 0?
        return netMap

    # Generates a list of net filter phrases using the local netMap
    # Currently all nets are included as filter phrases
    # Additionally, differential Nets get a special filter phrase
    def createNetFilterSuggestions(self):
        netFilterList = ['*']
        netList = [self.netMap[item].GetNetname() for item in self.netMap]
        diffMap = {'+': '-', 'P': 'N', '-': '+', 'N': 'P'}
        regexMap = {'+': '[+-]', '-': '[+-]', 'P': '[PN]', 'N': '[PN]'}
        invertDiffNet = lambda netName : netName[0:-1] + diffMap[netName[-1]]
        isDiffNet = lambda netName : True if netName[-1] in diffMap.keys() else False

        # Translate board nets into a filter list
        for netName in netList:
            if isDiffNet(netName) and invertDiffNet(netName) in netList:
                # If we have a +/- or P/N pair, we insert a regex entry once into the filter list
                filterText = netName[0:-1] + regexMap[netName[-1]]
                if (filterText not in netFilterList): netFilterList += [filterText]

            # Append every net to the filter list
            netFilterList += [netName]

        return netFilterList

    # Generates a RegEx string from a SimpleEx (which is a proprietary invention ;-))
    # The SimpleEx only supports [...] with single chars and * used as a wildcard
    def regExFromSimpleEx(self, simpleEx):
        # Escape the entire filter string. Unescape and remap specific characters that we want to allow
        subsTable = {r'\[':'[', r'\]':']', r'\*':'.*'}
        regEx = re.escape(simpleEx)
        for subsFrom, subsTo in subsTable.items(): regEx = regEx.replace(subsFrom, subsTo)
        return regEx

    def createVias(self, viaPoints, viaDrill, viaSize, netCode):
        newVias = []
        for viaPoint in viaPoints:
            newVia = pcbnew.VIA(self.boardObj)
            ts = 55
            newVia.SetTimeStamp(ts)  # adding a unique number as timestamp to mark this via as generated by this script
            self.boardObj.Add(newVia)

            newVia.SetPosition(pcbnew.wxPoint(viaPoint[0], viaPoint[1]))
            newVia.SetWidth(viaSize)
            newVia.SetDrill(viaDrill)
            newVia.SetViaType(pcbnew.VIA_THROUGH)
            newVia.SetNetCode(netCode)
            newVias += [newVia]

        return newVias

    def onDeleteClick(self, event):
        return self.mainDlg.EndModal(wx.ID_DELETE)
    
    def checkPads(self):
    ##Check vias collisions with all pads => all pads on all layers
        #wxPrint("Processing all pads...")
        #self.clearance = 0 #TBF
        self.clearance = self.boardObj.GetDesignSettings().GetDefault().GetClearance()
        #lboard = self.boardObj.ComputeBoundingBox(False)
        #origin = lboard.GetPosition()
        # Create an initial rectangle: all is set to "REASON_NO_SIGNAL"
        # get a margin to avoid out of range
        l_clearance = self.clearance + self.viaSize #+ self.size
        #x_limit = int((lboard.GetWidth() + l_clearance) / l_clearance) + 1
        #y_limit = int((lboard.GetHeight() + l_clearance) / l_clearance) + 1
        viasToRemove = []
        removed = False
        expansion = 1.6 # extra expansion to fix HitTest
        for pad in self.boardObj.GetPads():
            #wx.LogMessage(str(self.viaPointsSafe))
            #wx.LogMessage(str(pad.GetPosition()))
            #local_offset = max(pad.GetClearance(), self.clearance, max_target_area_clearance) + (self.size / 2)
            local_offset = max(pad.GetClearance(), self.clearance) + (self.viaSize / 2)
            max_size = max(pad.GetSize().x, pad.GetSize().y)
            
            #start_x = int(floor(((pad.GetPosition().x - (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))
            #stop_x = int(ceil(((pad.GetPosition().x + (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))
            
            #start_y = int(floor(((pad.GetPosition().y - (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))
            #stop_y = int(ceil(((pad.GetPosition().y + (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))
            
            #for x in range(start_x, stop_x + 1):
            #    for y in range(start_y, stop_y + 1):
            for viaPos in self.viaPointsSafe:
                if 1: #try:
                    #if isinstance(rectangle[x][y], ViaObject):
                    #start_rect = wxPoint(origin.x + (l_clearance * x) - local_offset,
                    #                     origin.y + (l_clearance * y) - local_offset)
                    #start_rect = pcbnew.wxPoint(viaPos[0] + (l_clearance * viaPos[0]) - local_offset,
                    #                    viaPos[1] + (l_clearance * viaPos[1]) - local_offset)
                    start_rect = pcbnew.wxPoint(viaPos[0] - local_offset*expansion,
                                        viaPos[1] - local_offset*expansion)
                    size_rect = pcbnew.wxSize(2 * expansion * local_offset, 2 * expansion * local_offset)
                    wxLogDebug(str(pcbnew.ToMM(start_rect))+'::'+str(pcbnew.ToMM(size_rect)),debug)
                    if pad.HitTest(pcbnew.EDA_RECT(start_rect, size_rect), False):
                        #rectangle[x][y] = self.REASON_PAD
                        wxLogDebug('Hit on Pad: viaPos:'+str(viaPos),debug)
                        #self.viaPointsSafe.pop(i)
                        #self.viaPointsSafe.remove(viaPos)
                        viasToRemove.append(viaPos)
                        removed = True
                    #else:
                    #    viaPSafe.append(viaPos)
                else: #except:
                    wx.LogMessage("exception on Processing all pads...")
                #i+=1
            #self.viaPointSafe = viaPSafe
        #wx.LogMessage(str(viasToRemove))
        newPoints = [p for p in self.viaPointsSafe if p not in viasToRemove]
        #wx.LogMessage(str(newPoints))
        #wx.LogMessage(str(len(newPoints)))
        self.viaPointsSafe = newPoints
        return removed
        
    def checkTracks(self):
    ##Check vias collisions with all tracks
        #self.clearance = 0 #TBF
        self.clearance = self.boardObj.GetDesignSettings().GetDefault().GetClearance()
        #lboard = self.boardObj.ComputeBoundingBox(False)
        #origin = lboard.GetPosition()
        # Create an initial rectangle: all is set to "REASON_NO_SIGNAL"
        # get a margin to avoid out of range
        l_clearance = self.clearance + self.viaSize #+ self.size
        #wxLogDebug(str(l_clearance),True)
        #x_limit = int((lboard.GetWidth() + l_clearance) / l_clearance) + 1
        #y_limit = int((lboard.GetHeight() + l_clearance) / l_clearance) + 1
        viasToRemove = []
        removed = False
        expansion = 2 # extra expansion to fix HitTest
        for track in self.boardObj.GetTracks():
            #wx.LogMessage(str(self.viaPointsSafe))
            #wx.LogMessage(str(pad.GetPosition()))
            #local_offset = max(pad.GetClearance(), self.clearance, max_target_area_clearance) + (self.size / 2)
            local_offset = max(track.GetClearance(), self.clearance) + (self.viaSize / 2)
            #wxLogDebug(str(max_size),True)
            #max_size = max(pad.GetSize().x, pad.GetSize().y)
            
            #start_x = int(floor(((pad.GetPosition().x - (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))
            #stop_x = int(ceil(((pad.GetPosition().x + (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))
            
            #start_y = int(floor(((pad.GetPosition().y - (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))
            #stop_y = int(ceil(((pad.GetPosition().y + (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))
            
            #for x in range(start_x, stop_x + 1):
            #    for y in range(start_y, stop_y + 1):
            #wx.LogMessage(str(getTrackAngleRadians(track)))
            angle = abs(math.degrees(getTrackAngleRadians(track)))
            if (angle > 15 and angle <75) or (angle > 105 and angle <165) or (angle > 195 and angle <255) or (angle > 285 and angle <345):
                expansion = 1.4 # extra expansion to fix HitTest
                #wx.LogMessage(str(angle)+'::'+str(expansion))
            else:
                expansion = 2.0 # extra expansion to fix HitTest
                #wx.LogMessage(str(angle)+'::'+str(expansion))
            for viaPos in self.viaPointsSafe:
                if 1: #try:
                    #if isinstance(rectangle[x][y], ViaObject):
                    #start_rect = wxPoint(origin.x + (l_clearance * x) - local_offset,
                    #                     origin.y + (l_clearance * y) - local_offset)
                    #start_rect = pcbnew.wxPoint(viaPos[0] + (l_clearance * viaPos[0]) - local_offset,
                    #                    viaPos[1] + (l_clearance * viaPos[1]) - local_offset)
                    start_rect = pcbnew.wxPoint(viaPos[0] - local_offset*expansion,
                                        viaPos[1] - local_offset*expansion)
                    size_rect = pcbnew.wxSize(2 * expansion * local_offset, 2 * expansion * local_offset)
                    wxLogDebug(str(pcbnew.ToMM(start_rect))+'::'+str(pcbnew.ToMM(size_rect)),debug)
                    #wxLogDebug(str(track.GetNetCode()),True)
                    #wxLogDebug(str(self.viaNetId),True)
                    #wxLogDebug(str(type(track)),True)
                    if track.GetNetCode() != self.viaNetId or type(track) != pcbnew.TRACK: #PCB_VIA_T:
                        #wxLogDebug('here',True)
                        #if track.HitTest(pcbnew.EDA_RECT(start_rect, size_rect), False):
                        aContained=False;aAccuracy=0
                        if track.HitTest(pcbnew.EDA_RECT(start_rect, size_rect), aContained, aAccuracy):
                            #rectangle[x][y] = self.REASON_PAD
                            wxLogDebug('Hit on Track: viaPos:'+str(viaPos),debug)
                            #self.viaPointsSafe.pop(i)
                            #self.viaPointsSafe.remove(viaPos)
                            viasToRemove.append(viaPos)
                            removed = True
                        #else:
                        #    viaPSafe.append(viaPos)
                else: #except:
                    wx.LogMessage("exception on Processing all tracks...")
                #i+=1
            #self.viaPointSafe = viaPSafe
        #wx.LogMessage(str(viasToRemove))
        newPoints = [p for p in self.viaPointsSafe if p not in viasToRemove]
        #wx.LogMessage(str(newPoints))
        #wx.LogMessage(str(len(newPoints)))
        self.viaPointsSafe = newPoints
        return removed
# ------------------------------------------------------------------------------------
    
    def DoKeyPress(self, event):
        if event.GetKeyCode() == wx.WXK_RETURN: 
            self.mainDlg.EndModal(wx.ID_OK)
        else:
            event.Skip()
    
    def selfToMainDialog(self):
        self.mainDlg.lstLayer.SetItems(list(self.layerMap.values()))  #maui
        self.mainDlg.lstLayer.SetSelection(self.layerId)
        self.mainDlg.txtNetFilter.SetItems(self.netFilterList)
        self.mainDlg.txtNetFilter.SetSelection(self.netFilterList.index(self.netFilter))
        self.mainDlg.txtViaOffset.SetValue(str(pcbnew.ToMM(self.viaOffset)))
        self.mainDlg.txtViaPitch.SetValue(str(pcbnew.ToMM(self.viaPitch)))
        self.mainDlg.txtViaDrill.SetValue(str(pcbnew.ToMM(self.viaDrill)))
        self.mainDlg.txtViaSize.SetValue(str(pcbnew.ToMM(self.viaSize)))
        self.mainDlg.txtViaOffset.Bind(wx.EVT_KEY_DOWN, self.DoKeyPress)
        #self.mainDlg.txtViaOffset.Bind(wx.EVT_TEXT_ENTER, self.mainDlg.EndModal(wx.ID_OK))
        self.mainDlg.txtViaPitch.Bind(wx.EVT_KEY_DOWN, self.DoKeyPress)
        self.mainDlg.txtViaDrill.Bind(wx.EVT_KEY_DOWN, self.DoKeyPress)
        self.mainDlg.txtViaSize.Bind(wx.EVT_KEY_DOWN, self.DoKeyPress)
        
        self.mainDlg.lstViaNet.SetItems([item.GetNetname() for item in self.netMap.values()])
        for i, item  in enumerate (self.netMap.values()):
            if self.mainDlg.lstViaNet.GetString(i) in ["GND", "/GND"]:
                self.mainDlg.lstViaNet.SetSelection(i)
                break
        self.mainDlg.chkNetFilter.SetValue(self.isNetFilterChecked)
        self.mainDlg.txtNetFilter.Enable(self.isNetFilterChecked)
        self.mainDlg.chkLayer.SetValue(self.isLayerChecked)
        self.mainDlg.lstLayer.Enable(self.isLayerChecked)
        self.mainDlg.chkIncludeDrawing.SetValue(self.isIncludeDrawingChecked)
        self.mainDlg.chkIncludeSelection.SetValue(self.isIncludeSelectionChecked)
        self.mainDlg.chkDebugDump.SetValue(self.isDebugDumpChecked)
        self.mainDlg.chkRemoveViasWithClearanceViolation.SetValue(self.isRemoveViasWithClearanceViolationChecked)
        self.mainDlg.chkSameNetZoneViasOnly.SetValue(self.isSameNetZoneViasOnlyChecked)
        self.mainDlg.m_buttonDelete.Bind(wx.EVT_BUTTON, self.onDeleteClick)
        # hiding unimplemented controls
        #self.mainDlg.chkRemoveViasWithClearanceViolation.Hide()
        self.mainDlg.chkSameNetZoneViasOnly.Hide()

    def mainDialogToSelf(self):
        self.netFilter = self.mainDlg.txtNetFilter.GetValue()
        if len(list(self.layerMap.keys())) > 0:
            self.layerId = list(self.layerMap.keys())[self.mainDlg.lstLayer.GetSelection()]   #maui
        self.viaOffset = pcbnew.FromMM(float(self.mainDlg.txtViaOffset.GetValue().replace(',','.')))
        self.viaPitch = pcbnew.FromMM(float(self.mainDlg.txtViaPitch.GetValue().replace(',','.')))
        self.viaDrill = pcbnew.FromMM(float(self.mainDlg.txtViaDrill.GetValue().replace(',','.')))
        self.viaSize = pcbnew.FromMM(float(self.mainDlg.txtViaSize.GetValue().replace(',','.')))
        if len(list(self.netMap.keys())) > 0:
            self.viaNetId = list(self.netMap.keys())[self.mainDlg.lstViaNet.GetSelection()]   #maui
        self.isNetFilterChecked = self.mainDlg.chkNetFilter.GetValue()
        self.isLayerChecked = self.mainDlg.chkLayer.GetValue()
        self.isIncludeDrawingChecked = self.mainDlg.chkIncludeDrawing.GetValue()
        self.isIncludeSelectionChecked = self.mainDlg.chkIncludeSelection.GetValue()
        self.isDebugDumpChecked = self.mainDlg.chkDebugDump.GetValue()
        self.isSameNetZoneViasOnlyChecked = self.mainDlg.chkSameNetZoneViasOnly.GetValue()
        self.isRemoveViasWithClearanceViolationChecked = self.mainDlg.chkRemoveViasWithClearanceViolation.GetValue()

    def Run(self):
        #check for pyclipper lib
        pyclip = False
        try:
            import pyclipper
            pyclip = True
            # import pyclipper; pyclipper.__file__
        except:
            #error exception if pyclipper lib is missing
            import sys, os
            from sys import platform as _platform
            if _platform == "linux" or _platform == "linux2":
                # linux
                if sys.version_info.major == 3 and sys.version_info.minor == 6:
                    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),'python-pyclipper','py3-6-linux-64'))
                    #wx.LogMessage(os.path.join(os.path.dirname(os.path.abspath(__file__)),'python-pyclipper','py3-6-linux-64'))
                elif sys.version_info.major == 2 and sys.version_info.minor == 7:
                    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),'python-pyclipper','py2-7-linux-64'))
            elif _platform == "darwin":
                #osx
                sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),'python-pyclipper','py2-7-mac-64'))
            else:
                #win
                sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),'python-pyclipper','py2-7-win-64'))
            try:
                import pyclipper
                pyclip = True
            except:
                wdlg = wx.MessageDialog(None, u"\u2718 ERROR Missing KiCAD \'pyclipper\' python module",'ERROR message',wx.OK | wx.ICON_WARNING)# wx.ICON_ERROR)
                result = wdlg.ShowModal()
        if pyclip:
        #import pyclipper
            import os
            self.boardObj = pcbnew.GetBoard()
            self.boardDesignSettingsObj = self.boardObj.GetDesignSettings()
            self.boardPath = os.path.dirname(os.path.realpath(self.boardObj.GetFileName()))
            self.layerMap = self.getLayerMap()
            self.highlightedNetId = self.boardObj.GetHighLightNetCode()
            self.netMap = self.getNetMap()
            self.netFilterList = self.createNetFilterSuggestions()
            self.netFilter = self.netMap[self.highlightedNetId].GetNetname() if self.highlightedNetId != -1 else self.netFilterList[0]
            self.viaSize = self.boardDesignSettingsObj.GetCurrentViaSize()
            self.layerId = 0 #TODO: How to get currently selected layer?
            self.viaDrill = self.boardDesignSettingsObj.GetCurrentViaDrill()
            self.viaPitch = pcbnew.FromMM(1.0)
            self.viaOffset = pcbnew.FromMM(1.0)
            self.viaNetId = 0 #TODO: Maybe a better init value here. Try to find "GND" maybe?
            self.isNetFilterChecked = 1 if self.highlightedNetId != -1 else 0
            self.isLayerChecked = 0
            self.isIncludeDrawingChecked = 0
            self.isIncludeSelectionChecked = 1
            self.isDebugDumpChecked = 0
            self.isRemoveViasWithClearanceViolationChecked = 1
            self.isSameNetZoneViasOnlyChecked = 0
        
            self.mainDlg = MainDialog(None)
            self.selfToMainDialog()
            reply = self.mainDlg.ShowModal()
            if (reply == wx.ID_OK):
                # User pressed OK.
                # Assemble a list of pcbnew.BOARD_ITEMs derived objects that support GetStart/GetEnd and IsOnLayer
                self.mainDialogToSelf()
                lineObjects = []
        
                # Do we want to include net tracks?
                if (self.isNetFilterChecked):
                    # Find nets that match the generated regular expression and add their tracks to the list
                    netRegex = self.regExFromSimpleEx(self.netFilter)
                    for netId in self.netMap:
                        if re.match(netRegex, self.netMap[netId].GetNetname()):
                            for trackObject in self.boardObj.TracksInNet(netId):
                                lineObjects += [trackObject]
        
                # Do we want to include drawing segments?
                if (self.isIncludeDrawingChecked):
                    boardItem = self.boardObj.GetDrawings().GetFirst()
                    while boardItem is not None:
                        if pcbnew.DRAWSEGMENT.ClassOf(boardItem):
                            # A drawing segment (not a text or something else)
                            drawingObject = boardItem.Cast()
                            if drawingObject.GetShape() == pcbnew.S_SEGMENT:
                                # A straight line
                                lineObjects += [drawingObject]
        
                        boardItem = boardItem.Next()
                
                # Do we want to include track segments?
                if (self.isIncludeSelectionChecked):
                    for item in self.boardObj.GetTracks():
                        if type(item) is pcbnew.TRACK and item.IsSelected():
                            lineObjects += [item]
                    
                # Do we want to filter the generated lines by layer?
                if (self.isLayerChecked):
                    # Filter by layer
                    # TODO: Make layer selection also a regex
                    lineObjects = [lineObject for lineObject in lineObjects if lineObject.IsOnLayer(self.layerId)]
        
                # Generate a path list from the pcbnew.BOARD_ITEM objects
                self.pathList =  [[ [lineObject.GetStart()[0], lineObject.GetStart()[1]],
                                    [lineObject.GetEnd()[0],   lineObject.GetEnd()[1]]   ]
                                    for lineObject in lineObjects]
        
                # Generate via fence
                try:
                    viaPoints = generateViaFence(self.pathList, self.viaOffset, self.viaPitch)
                except:
                    wx.LogMessage ('exception on via fence generation')
                    viaPoints = []
        
                if (self.isDebugDumpChecked):
                    self.viaPoints = viaPoints
                    self.dumpJSON(os.path.join(self.boardPath, time.strftime("viafence-%Y%m%d-%H%M%S.json")))
        
                removed = False
                if (self.isRemoveViasWithClearanceViolationChecked):
                #if self.mainDlg.chkRemoveViasWithClearanceViolation.GetValue():
                    # Remove Vias that violate clearance to other things
                    # Check against other tracks
                    #wx.LogMessage('hereIam')
                    # removing generated & colliding vias
                    viaPointsSafe = []
                    for i,v in enumerate(viaPoints):
                        #clearance = v.GetClearance()
                        collision_found = False
                        tolerance = 1 + 0.2 
                        # This should be handled with Net Clearance
                        for j, vn in enumerate(viaPoints[i+1:]):
                            if distance (pcbnew.wxPoint(v[0], v[1]),pcbnew.wxPoint(vn[0], vn[1])) < int(self.viaSize*tolerance): # +clearance viasize+20%:
                                collision_found = True
                        if not collision_found:
                            viaPointsSafe.append(v)
                    self.viaPointsSafe = viaPointsSafe
                    #wx.LogMessage(str(len(self.viaPointsSafe)))
                    removed = self.checkPads()
                    remvd = self.checkTracks()
                    removed = removed or remvd
                else:
                    self.viaPointsSafe = viaPoints
                #wx.LogMessage(str(len(self.viaPointsSafe)))
                #self.checkPads()
                #wx.LogMessage(str(len(self.viaPointsSafe)))
                viaObjList = self.createVias(self.viaPointsSafe, self.viaDrill, self.viaSize, self.viaNetId)
                via_nbr = len(self.viaPointsSafe)
                msg = u'Placed {0:} Fencing Vias.\n\u26A0 Please run a DRC check on your board.'.format(str(via_nbr))
                if removed:
                    msg += u'\n\u26EC Removed DRC colliding vias.'
                wx.LogMessage(msg)
                #viaObjList = self.createVias(viaPoints, self.viaDrill, self.viaSize, self.viaNetId)
                #via_nbr = len(viaPoints)
                
            
            elif (reply == wx.ID_DELETE):
                #user clicked ('Delete Fence Vias')
                target_tracks = filter(lambda x: ((x.Type() == pcbnew.PCB_VIA_T)and (x.GetTimeStamp() == 55)), self.boardObj.GetTracks())
                #wx.LogMessage(str(len(target_tracks)))
                target_tracks_cp = list(target_tracks)
                l = len (target_tracks_cp)
                for i in range(l): 
                    #if type(target_tracks_cp[i]) is TRACK and target_tracks_cp[i].IsSelected(): #item.GetNetname() == net_name:
                    self.boardObj.RemoveNative(target_tracks_cp[i])  #removing via
                #for via in target_tracks:
                #    #if via.GetTimeStamp() == 55:
                #    self.boardObj.RemoveNative(via)
                #    #wx.LogMessage('removing via')
                #pcbnew.Refresh()
            self.mainDlg.Destroy()  #the Dlg needs to be destroyed to release pcbnew

# TODO: Implement
#            if (self.isRemoveViasWithClearanceViolationChecked):
#                # Remove Vias that violate clearance to other things
#                # Check against other tracks
#                for viaObj in viaObjList:
#                    for track in self.boardObj.GetTracks():
#                        clearance = track.GetClearance(viaObj)
#                        if track.HitTest(False, clearance):
#                            self.boardObj.RemoveNative(viaObj)

# TODO: Implement
#            if (self.isSameNetZoneViasOnlyChecked):
#                # Keep via only if it is in a filled zone with the same net

#            import numpy as np
#            import matplotlib.pyplot as plt

#            for path in self.pathList:
#                plt.plot(np.array(path).T[0], np.array(path).T[1], linewidth=2)
#            for via in viaPoints:
#                plt.plot(via[0], via[1], 'o', markersize=10)


#            plt.ylim(plt.ylim()[::-1])
#            plt.axes().set_aspect('equal','box')
#            plt.show()
 