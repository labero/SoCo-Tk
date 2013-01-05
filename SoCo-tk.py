#!/usr/bin/env python

import Tkinter as tk
import logging, traceback
import tkMessageBox
import urllib
import base64
import StringIO as sio

try:
    import soco
except:
    logging.warning('Could not import soco, trying from local file')
    try:
        import sys
        sys.path.append('./SoCo')
        import soco
    except:
        logging.error('Could not find SoCo library')
        soco = None

try:
    from PIL import Image, ImageTk
except:
    logging.error('Could not import PIL')
    logging.error(traceback.format_exc())
    ImageTk = None
    Image = None

class WrappedSoCo(soco.SoCo):
    def __init__(self, ip):
        soco.SoCo.__init__(self, ip)
        self.get_speaker_info()
        
        invalid_keys = [key for key, value in self.speaker_info.items() if value is None]
        for key in invalid_keys:
            del self.speaker_info[key]
        
    def __str__(self):
        name = self.speaker_info['zone_name']
        if name is None:
            name = 'Unnamed'
        return name


class SonosList(tk.PanedWindow):

    def __init__(self, parent):
        self.__parent = parent
        tk.PanedWindow.__init__(self, parent, sashrelief = tk.RAISED)

        self.__parent.protocol('WM_DELETE_WINDOW', self.__parent.quit)
        
        self.grid(row = 0,
                  column = 0,
                  ipadx = 5,
                  ipady = 5,
                  sticky = 'news')

        self.__speakers = {}
        self.__listContent = []

        self._controlButtons = {}
        self._infoWidget = {}

        self.__lastSelected = None
        self.__lastImage = None
        self.empty_info = '-'

        self._createWidgets()
        self._createMenu()

        parent.rowconfigure(0, weight = 1)
        parent.columnconfigure(0, weight = 1)
        self.rowconfigure(0, weight = 1)
        self.columnconfigure(0, weight = 1)

        self._addContent()

        self._updateButtons()

    def __del__(self):
        for speaker in self.__speakers.keys():
            del speaker

        self.__speakers.clear()

        del self.__listContent[:]

    def get_speaker_ips(self):
        disc = None
        try:
            disc = soco.SonosDiscovery()
            return disc.get_speaker_ips()
        finally:
            if disc: del disc

    def _addContent(self, force = False):
        ips = self.get_speaker_ips()

        speakers = []
        for ip in ips:
            speaker = WrappedSoCo(ip)
            if not speaker.speaker_info:
                logging.warning('Speaker %s does not have any info (probably a bridge), skipping...', ip)
                continue

            speakers.append(speaker)

        logging.debug('Found %d speaker(s)', len(speakers))
        if len(speakers) > 1:
            logging.debug('Sorting speakers based on name')
            speakers = sorted(speakers,
                              cmp = lambda a,b: cmp(str(a), str(b)))
        
        for speaker in speakers:
            self.__speakers[ip] = speaker
            self.__listContent.append(speaker)
            self._listbox.insert(tk.END, speaker)
        
    def _createWidgets(self):
        logging.debug('Creating widgets')
        # Left frame
        self._left = tk.Frame(self)
        self.add(self._left)
                          
        # Right frame
        self._right = tk.Frame(self)
        self.add(self._right)

        # Create Sonos list
        self._listbox = tk.Listbox(self._left,
                                   selectmode = tk.EXTENDED)

        self._listbox.bind('<<ListboxSelect>>', self._listboxSelected)

        
        self._listbox.grid(row = 0,
                           column = 0,
                           columnspan = 5,
                           padx = 5,
                           pady = 5,
                           sticky = 'news')
        
        self._createButtons()
                          
        self._left.rowconfigure(0, weight = 1)
        self._left.columnconfigure(0, weight = 1)

        self._right.rowconfigure(0, weight = 1)
        self._right.columnconfigure(0, weight = 1)

        self._info = tk.Frame(self._right)
        self._info.grid(row = 0,
                        column = 0,
                        padx = 5,
                        pady = 5,
                        sticky = 'news')

        self._info.rowconfigure(9, weight = 1)
        self._info.columnconfigure(1, weight = 1)

        self._createInfoWidgets()

    def _createInfoWidgets(self):
        infoIndex = 0

        ###################################
        # Title
        ###################################
        label = tk.Label(self._info, text = 'Title:')
        label.grid(row = infoIndex,
                   column = 0,
                   sticky = 'w')
        
        self._infoWidget['title'] = tk.Label(self._info,
                                             text = self.empty_info,
                                             anchor = 'w')
        
        self._infoWidget['title'].grid(row = infoIndex,
                                       column = 1,
                                       padx = 5,
                                       pady = 5,
                                       sticky = 'we')
        infoIndex += 1

        ###################################
        # Artist
        ###################################
        label = tk.Label(self._info, text = 'Artist:')
        label.grid(row = infoIndex,
                   column = 0,
                   sticky = 'w')
        
        self._infoWidget['artist'] = tk.Label(self._info,
                                             text = self.empty_info,
                                             anchor = 'w')
        
        self._infoWidget['artist'].grid(row = infoIndex,
                                        column = 1,
                                        padx = 5,
                                        pady = 5,
                                        sticky = 'we')
        infoIndex += 1

        ###################################
        # Album
        ###################################
        label = tk.Label(self._info, text = 'Album:')
        label.grid(row = infoIndex,
                   column = 0,
                   sticky = 'w')
        
        self._infoWidget['album'] = tk.Label(self._info,
                                             text = self.empty_info,
                                             anchor = 'w')
        
        self._infoWidget['album'].grid(row = infoIndex,
                                       column = 1,
                                       padx = 5,
                                       pady = 5,
                                       sticky = 'we')
        infoIndex += 1

        ###################################
        # Volume
        ###################################
        label = tk.Label(self._info, text = 'Volume:')
        label.grid(row = infoIndex,
                   column = 0,
                   sticky = 'w')
        
        self._infoWidget['volume'] = tk.Scale(self._info,
                                              from_ = 0,
                                              to = 100,
                                              tickinterval = 10,
                                              orient = tk.HORIZONTAL)
        
        self._infoWidget['volume'].grid(row = infoIndex,
                                        column = 1,
                                        padx = 5,
                                        pady = 5,
                                        sticky = 'we')

        self._infoWidget['volume'].bind('<ButtonRelease-1>', self._volumeChanged)
        infoIndex += 1

        ###################################
        # Album art
        ###################################
        self._infoWidget['album_art'] = tk.Label(self._info,
                                                 image = tk.PhotoImage(),
                                                 width = 150,
                                                 height = 150)
        
        self._infoWidget['album_art'].grid(row = infoIndex,
                                           column = 1,
                                           padx = 5,
                                           pady = 5,
                                           sticky = 'nw')

    def __getSelectedSpeaker(self, widget = None):
        if widget is None:
            widget = self._listbox

        selection = widget.curselection()
        if not selection:
            return None, None

        index = int(selection[0])
        
        assert len(self.__listContent) > index
        speaker = self.__listContent[index]

        return speaker, index
        
    def _volumeChanged(self, evt):
        speaker, index = self.__getSelectedSpeaker()
        
        if index is None:
            logging.debug('Nothing selected')
            return

        volume = self._infoWidget['volume'].get()

        logging.debug('Changing volume to: %d', volume)
        speaker.volume(volume)
        
    def _listboxSelected(self, evt):
        # Note here that Tkinter passes an event object to onselect()
        w = evt.widget
        
        speaker, index = self.__getSelectedSpeaker(w)

        if self.__lastSelected == index: return
        self.__lastSelected = index

        self.showSpeakerInfo(speaker)
        self._updateButtons()
        
        if index is None:
            logging.debug('Nothing selected')
            self.__lastSelected = None
            return
        
        logging.debug('Zoneplayer: "%s"', speaker)
        

    def showSpeakerInfo(self, speaker):
        if not isinstance(speaker, soco.SoCo) and\
           speaker is not None:
            raise TypeError('Unsupported type: %s', type(speaker))

        if speaker is None:
            for info in self._infoWidget.keys():
                if info == 'volume':
                    self._infoWidget[info].set(0)
                    continue
                elif info == 'album_art':
                    self._infoWidget[info].config(image = None)
                    if self.__lastImage:
                        del self.__lastImage
                        self.__lastImage = None
                    continue
                
                self._infoWidget[info].config(text = self.empty_info)
            return

        logging.info('Receive speaker info from: "%s"' % speaker)
        try:
            track = speaker.get_current_track_info()

            track['volume'] = speaker.volume()
            
            for info, value in track.items():
                if info == 'album_art':
                    self.__setAlbumArt(value)
                    continue
                elif info == 'volume':
                    self._infoWidget[info].set(value)
                    continue
                elif info not in self._infoWidget:
                    logging.debug('Skipping info "%s": "%s"', info, value)
                    continue
                
                label = self._infoWidget[info]
                label.config(text = value if value else self.empty_info)
        except:
            errmsg = traceback.format_exc()
            logging.error(errmsg)
            tkMessageBox.showerror(title = 'Speaker info...',
                                   message = 'Could not receive speaker information')
            

    def __setAlbumArt(self, url):
        if ImageTk is None:
            logging.warning('python-imaging-tk lib missing, skipping album art')
            return
        
        connection = None
        newImage = None
        
        # Receive Album art, resize it and show it
        try:
            connection = urllib.urlopen(url)
            raw_data = connection.read()
            b64 = base64.encodestring(raw_data)
            image = Image.open(sio.StringIO(raw_data))
            widgetConfig = self._infoWidget['album_art'].config()
            thumbSize = (int(widgetConfig['width'][4]),
                         int(widgetConfig['height'][4]))

            logging.debug('Resizing album art to: %s', thumbSize)
            image.thumbnail(thumbSize,
                            Image.ANTIALIAS)
            newImage = ImageTk.PhotoImage(image = image)
            self._infoWidget['album_art'].config(image = newImage)
        except:
            logging.error('Could not set album art, skipping...')
            logging.error(traceback.format_exc())
        finally:
            if connection: connection.close()
            
            if self.__lastImage: del self.__lastImage
            self.__lastImage = newImage

    def _updateButtons(self):
        logging.debug('Updating control buttons')
        speaker, index = self.__getSelectedSpeaker()
        
        newState = tk.ACTIVE if speaker else tk.DISABLED
        for button in self._controlButtons.values():
            button.config(state = newState)
        
    def _createButtons(self):
        logging.debug('Creating buttons')
        buttonIndex = 0
        buttonWidth = 2
        
        button_prev = tk.Button(self._left,
                                width = buttonWidth,
                                command = self.__previous,
                                text = '<<')
        button_prev.grid(row = 1,
                         column = buttonIndex,
                         padx = 5,
                         pady = 5,
                         sticky = 'w')
        self._controlButtons['previous'] = button_prev
        buttonIndex += 1

        button_pause = tk.Button(self._left,
                                 width = buttonWidth,
                                 command = self.__pause,
                                 text = '||')
        button_pause.grid(row = 1,
                          column = buttonIndex,
                          padx = 5,
                          pady = 5,
                          sticky = 'w')
        self._controlButtons['pause'] = button_pause
        buttonIndex += 1

        button_play = tk.Button(self._left,
                                 width = buttonWidth,
                                 command = self.__play,
                                 text = '>')
        button_play.grid(row = 1,
                         column = buttonIndex,
                         padx = 5,
                         pady = 5,
                         sticky = 'w')
        self._controlButtons['play'] = button_play
        buttonIndex += 1

        button_next = tk.Button(self._left,
                                width = buttonWidth,
                                command = self.__next,
                                text = '>>')
        button_next.grid(row = 1,
                         column = buttonIndex,
                         padx = 5,
                         pady = 5,
                         sticky = 'w')
        self._controlButtons['next'] = button_next
        buttonIndex += 1

    def _createMenu(self):
        logging.debug('Creating menu')
        self._menubar = tk.Menu(self)
        self.__parent.config(menu = self._menubar)
        
        # File menu
        self._filemenu = tk.Menu(self._menubar, tearoff=0)
        self._menubar.add_cascade(label="File", menu=self._filemenu)

        #TODO: force update
##        self._filemenu.add_command(label="Refresh", command=self._addContent)
        
        self._filemenu.add_command(label="Exit", command=self.__parent.quit)

    def __previous(self):
        speaker, index = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.previous()
        self.showSpeakerInfo(speaker)
        
    def __next(self):
        speaker, index = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.next()
        self.showSpeakerInfo(speaker)

    def __pause(self):
        speaker, index = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.pause()
        self.showSpeakerInfo(speaker)

    def __play(self):
        speaker, index = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.play()
        self.showSpeakerInfo(speaker)

def main(root):
    logging.debug('Main')
    sonosList = SonosList(root)
    sonosList.mainloop()

if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)10s: %(message)s', level=logging.DEBUG)
    
    root = tk.Tk()
    try:
        root.wm_title('SoCo')
        root.minsize(600,400)
        main(root)
##    except:
##        logging.debug(traceback.format_exc())
    finally:
        root.quit()
        root.destroy()
