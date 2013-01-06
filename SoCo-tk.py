#!/usr/bin/env python

import Tkinter as tk
import logging, traceback
logging.basicConfig(format='%(asctime)s %(levelname)10s: %(message)s', level = logging.DEBUG)

import tkMessageBox
import urllib
import base64
import platform, os
import StringIO as sio

import sqlite3 as sql
import contextlib as clib

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

USER_DATA = None

if platform.system() == 'Windows':
    USER_DATA = os.path.join(os.getenv('APPDATA'), 'SoCo-Tk')
elif platform.system() == 'Linux':
    USER_DATA = '%(sep)shome%(sep)s%(name)s%(sep)s.config%(sep)sSoCo-Tk%(sep)s' % {
    'sep' : os.sep,
    'name': os.environ['LOGNAME']
    }    
##elif platform.system() == 'Mac':
##    pass


class WrappedSoCo(soco.SoCo):
    def __init__(self, ip, get_info = True):
        soco.SoCo.__init__(self, ip)
        if get_info: self.get_speaker_info()
        
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

        self.__parent.protocol('WM_DELETE_WINDOW', self._cleanExit)
        
        self.grid(row = 0,
                  column = 0,
                  ipadx = 5,
                  ipady = 5,
                  sticky = 'news')

        self.__listContent = []
        self.__queueContent = []

        self._controlButtons = {}
        self._infoWidget = {}

        self.__lastSelected = None
        self.__lastImage = None
        self.__currentSpeaker = None
        self._connection = None

        self.empty_info = '-'
        self.labelQueue = '%(artist)s - %(title)s'

        self._createWidgets()
        self._createMenu()

##        self.sash_place(0,150,400)
##        self.sash_place(1,400,400)

        parent.rowconfigure(0, weight = 1)
        parent.columnconfigure(0, weight = 1)
        self.rowconfigure(0, weight = 1)
        self.columnconfigure(0, weight = 1)

        self._loadSettings()
        self._updateButtons()



    def destroy(self):
        try:
            del self.__listContent[:]
            del self.__queueContent[:]
            if self.__currentSpeaker:
                del self.__currentSpeaker
                self.__currentSpeaker = None

            if self._connection:
                logging.info('Closing database connection')
                self._connection.close()
                self._connection = None
        except:
            logging.error('Error while destroying')
            logging.error(traceback.format_exc())
        
    def __del__(self):
        self.destroy()

    def get_speaker_ips(self):
        disc = None
        try:
            disc = soco.SonosDiscovery()
            return disc.get_speaker_ips()
        finally:
            if disc: del disc

    def scanSpeakers(self):
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

        self._storeSpeakers(speakers)
        self.__addSpeakers(speakers)

    def _cleanExit(self):
        try:
            geometry = self.__parent.geometry()
            if geometry:
                logging.debug('Storing geometry: "%s"', geometry)
                self.__setConfig('window_geometry', geometry)

            listOfPanes = self.panes()
            sashes = []
            for index in range(len(listOfPanes) - 1):
                x, y = self.sash_coord(index)
                sashes.append(':'.join((str(index),
                                        str(x),
                                        str(y))))

            finalSashValue = ','.join(sashes)
            logging.debug('Storing sashes: "%s"', finalSashValue)
            self.__setConfig('sash_coordinates', finalSashValue)
                
        except:
            logging.error('Error making clean exit')
            logging.error(traceback.format_exc())
        finally:
            self.destroy()
            self.__parent.quit()
            

    def __addSpeakers(self, speakers):
        logging.debug('Deleting all items from list')
        self._listbox.delete(0, tk.END)
        del self.__listContent[:]
        self.__listContent = []

        if not speakers:
            logging.debug('No speakers to add, returning')
            return
        
        logging.debug('Inserting new items (%d)', len(speakers))
        for speaker in speakers:
            self.__listContent.append(speaker)
            self._listbox.insert(tk.END, speaker)
        
    def _createWidgets(self):
        logging.debug('Creating widgets')
        # Left frame
        self._left = tk.Frame(self)
        self.add(self._left)
                          
        # Center frame
        self._center = tk.Frame(self)
        self.add(self._center)

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


        # Create queue list
        scrollbar = tk.Scrollbar(self._right)
        self._queuebox = tk.Listbox(self._right,
                                    selectmode = tk.EXTENDED)

        scrollbar.config(command = self._queuebox.yview)
        self._queuebox.config(yscrollcommand = scrollbar.set)
        self._queuebox.bind('<Double-Button-1>', self._playSelectedQueueItem)
        
        scrollbar.grid(row = 0,
                       column = 1,
                       pady = 5,
                       sticky = 'ns')
        
        self._queuebox.grid(row = 0,
                            column = 0,
                            padx = 5,
                            pady = 5,
                            sticky = 'news')

        self._createButtons()
                          
        self._left.rowconfigure(0, weight = 1)
        self._left.columnconfigure(0, weight = 1)

        self._center.rowconfigure(0, weight = 1)
        self._center.columnconfigure(0, weight = 1)

        self._right.rowconfigure(0, weight = 1)
        self._right.columnconfigure(0, weight = 1)

        self._info = tk.Frame(self._center)
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

    def __getSelectedSpeaker(self):
        if self.__currentSpeaker:
            return self.__currentSpeaker
        
        widget = self._listbox

        selection = widget.curselection()
        if not selection:
            return None

        index = int(selection[0])
        
        assert len(self.__listContent) > index
        speaker = self.__listContent[index]

        return speaker

    def __getSelectedQueueItem(self):
        widget = self._queuebox

        selection = widget.curselection()
        if not selection:
            return None, None

        index = int(selection[0])

        assert len(self.__queueContent) > index
        track = self.__queueContent[index]

        return track, index
        
    def _volumeChanged(self, evt):
        if not self.__currentSpeaker:
            logging.warning('No speaker selected')
            return
        
        speaker = self.__currentSpeaker
        volume = self._infoWidget['volume'].get()

        logging.debug('Changing volume to: %d', volume)
        speaker.volume(volume)
        
    def _listboxSelected(self, evt):
        # Note here that Tkinter passes an event object to onselect()
        widget = evt.widget

        selection = widget.curselection()
        if not selection:
            self.showSpeakerInfo(None)            
            self._updateButtons()
            return

        index = int(selection[0])
        
        assert len(self.__listContent) > index
        speaker = self.__listContent[index]

        if speaker == self.__currentSpeaker:
            logging.info('Speaker already selected, skipping')
            return
        
        self.showSpeakerInfo(speaker)
        self._updateButtons()
                
        logging.debug('Zoneplayer: "%s"', speaker)

        logging.debug('Storing last_selected: %s' % speaker.speaker_info['uid'])
        self.__setConfig('last_selected', speaker.speaker_info['uid'])
        

    def showSpeakerInfo(self, speaker):
        if not isinstance(speaker, soco.SoCo) and\
           speaker is not None:
            raise TypeError('Unsupported type: %s', type(speaker))

        self.__currentSpeaker = speaker
        
        newState = tk.ACTIVE if speaker is not None else tk.DISABLED
        self._infoWidget['volume'].config(state = newState)
        
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

        #######################
        # Load speaker info
        #######################
        try:
            logging.info('Receive speaker info from: "%s"' % speaker)
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

        #######################
        # Load queue
        #######################
        try:
            logging.info('Gettting queue from speaker')
            queue = speaker.get_queue()

            logging.debug('Deleting old items')
            self._queuebox.delete(0, tk.END)
            del self.__queueContent[:]
            self.__queueContent = []

            logging.debug('Inserting items (%d) to listbox', len(queue))
            for item in queue:
                string = self.labelQueue % item
                self.__queueContent.append(item)
                self._queuebox.insert(tk.END, string)
        except:
            errmsg = traceback.format_exc()
            logging.error(errmsg)
            tkMessageBox.showerror(title = 'Queue...',
                                   message = 'Could not receive speaker queue')
            

    def __setAlbumArt(self, url):
        if ImageTk is None:
            logging.warning('python-imaging-tk lib missing, skipping album art')
            return

        if not url:
            logging.warning('url is empty, returnning')
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
        speaker = self.__getSelectedSpeaker()
        
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

        self._filemenu.add_command(label="Scan for speakers", command=self.scanSpeakers)
        
        self._filemenu.add_command(label="Exit", command=self._cleanExit)


    def _playSelectedQueueItem(self, evt):
        try:
            track, track_index = self.__getSelectedQueueItem()
            speaker = self.__getSelectedSpeaker()

            if speaker is None or\
               track_index is None:
                logging.warning('Could not get track or speaker (%s, %s)', track_index, speaker)
                return
            
            speaker.play_from_queue(track_index)
            self.showSpeakerInfo(speaker)
        except:
            logging.error('Could not play queue item')
            logging.error(traceback.format_exc())
            tkMessageBox.showerror(title = 'Queue...',
                                   message = 'Error playing queue item, please check error log for description')
        

    def __previous(self):
        speaker = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.previous()
        self.showSpeakerInfo(speaker)
        
    def __next(self):
        speaker = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.next()
        self.showSpeakerInfo(speaker)

    def __pause(self):
        speaker = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.pause()
        self.showSpeakerInfo(speaker)

    def __play(self):
        speaker = self.__getSelectedSpeaker()
        if not speaker:
            raise SystemError('No speaker selected, this should not happend')

        speaker.play()
        self.showSpeakerInfo(speaker)

    def _loadSettings(self):
        # Connect to database
        dbPath = os.path.join(USER_DATA, 'SoCo-Tk.sqlite')

        createStructure = False
        if not os.path.exists(dbPath):
            logging.info('Database "%s" not found, creating', dbPath)
            createStructure = True

            if not os.path.exists(USER_DATA):
                logging.info('Creating directory structure')
                os.makedirs(USER_DATA)

        logging.info('Connecting: %s', dbPath)
        self._connection = sql.connect(dbPath)
        self._connection.row_factory = sql.Row

        if createStructure:
            self._createSettingsDB()

        # Load window geometry
        geometry = self.__getConfig('window_geometry')
        if geometry:
            try:
                logging.info('Found geometry "%s", applying', geometry)
                self.__parent.geometry(geometry)
            except:
                logging.error('Could not set window geometry')
                logging.error(traceback.format_exc())

        # Load speakers
        speakers = self._loadSpeakers()
        if speakers:
            self.__addSpeakers(speakers)
        else:
            message = 'No speakers found in your local configuration' \
                      ', do you want to scan for speakers?'
            
            doscan = tkMessageBox.askyesno(title = 'Scan...',
                                           message = message)
            if doscan: self.scanSpeakers()

        # Load last selected speaker
        selected_speaker_uid = self.__getConfig('last_selected')
        logging.debug('Last selected speaker: %s', selected_speaker_uid)

        selectIndex = None
        selectSpeaker = None
        for index, speaker in enumerate(self.__listContent):
            if speaker.speaker_info['uid'] == selected_speaker_uid:
                selectIndex = index
                selectSpeaker = speaker
                break

        if selectIndex is not None:
            self._listbox.selection_anchor(selectIndex)
            self._listbox.selection_set(selectIndex)
            self._listbox.see(selectIndex)
            self.showSpeakerInfo(speaker)

##        # Load sash_coordinates
##        sashes = self.__getConfig('sash_coordinates')
##        if sashes:
##            for sash_info in sashes.split(','):
##                if len(sash_info) < 1: continue
##                try:
##                    logging.debug('Setting sash: "%s"' % sash_info)
##                    index, x, y = map(int, sash_info.split(':'))
##                    self.sash_place(index, x, y)
##                except:
##                    logging.error('Could not set sash: "%s"' % sash_info)
##                    logging.error(traceback.format_exc())
##
##            

    def _storeSpeakers(self, speakers):
        logging.debug('Removing old speakers')
        self._connection.execute('DELETE FROM speakers').close()
        self._connection.commit()

        __sql = '''
            INSERT INTO speakers(
                name,
                ip,
                uid,
                serial,
                mac
            ) VALUES (?, ?, ?, ?, ?)
        '''
        
        logging.debug('Storing speakers (size: %d)', len(speakers))
        for speaker in speakers:
            try:
                params = (
                    speaker.speaker_info['zone_name'],
                    speaker.speaker_ip,
                    speaker.speaker_info['uid'],
                    speaker.speaker_info['serial_number'],
                    speaker.speaker_info['mac_address'],
                    )
                self._connection.execute(__sql, params).close()
            except:
                logging.error('Could not insert speaker: %s', speaker)
                logging.error(traceback.format_exc())
                
        self._connection.commit()
        
    def _loadSpeakers(self):
        logging.info('Loading speakers from config')
        __sql = '''
            SELECT
                speaker_id,
                name,
                ip,
                uid,
                serial,
                mac
            FROM speakers
        '''

        speakers = []
        with clib.closing(self._connection.execute(__sql)) as cur:
            for row in cur:
                speaker_id = None
                try:
                    speaker_id = row['speaker_id']
                    speaker = WrappedSoCo(row['ip'], get_info = False)
                    speaker.speaker_info['zone_name'] =         row['name']
                    speaker.speaker_info['uid'] =               row['uid']
                    speaker.speaker_info['serial_number'] =     row['serial']
                    speaker.speaker_info['mac_address'] =       row['mac']
                    speakers.append(speaker)
                except:
                    logging.error('Could not load speaker (id: %s)' % speaker_id)
                    logging.error(traceback.format_exc())

        return speakers

    def __setConfig(self, settingName, value):
        assert settingName is not None

        __sql = 'INSERT OR REPLACE INTO config (name, value) VALUES (?, ?)'

        self._connection.execute(__sql, (settingName, value)).close()
        self._connection.commit()
        
    def __getConfig(self, settingName):
        assert settingName is not None

        __sql = 'SELECT value FROM config WHERE name = ? LIMIT 1'

        with clib.closing(self._connection.execute(__sql, (settingName, ))) as cur:
            row = cur.fetchone()

            if not row:
                return None
            
            return row['value']

    def _createSettingsDB(self):
        logging.debug('Creating tables')
        self._connection.executescript('''
            CREATE TABLE IF NOT EXISTS config(
                config_id   INTEGER,
                name        TEXT UNIQUE,
                value       TEXT,
                PRIMARY KEY(config_id)
            );
                
            CREATE TABLE IF NOT EXISTS speakers(
                speaker_id  INTEGER,
                name        TEXT,
                ip          TEXT,
                uid         TEXT,
                serial      TEXT,
                mac         TEXT,
                PRIMARY KEY(speaker_id)
            );
                
            CREATE TABLE IF NOT EXISTS images(
                image_id        INTEGER,
                uri             TEXT,
                image           BLOB,
                image_size_id   INTEGER,
                PRIMARY KEY(image_id)
            );

            CREATE TABLE IF NOT EXISTS image_size(
                image_size_id   INTEGER,
                label           TEXT,
                width           INTEGER,
                height          INTEGER,
                PRIMARY KEY(image_size_id)
            );
        ''').close()

        logging.debug('Creating index')
        self._connection.execute('''
            CREATE INDEX IF NOT EXISTS idx_image_size_label ON image_size(label)
        ''').close()

        self._connection.execute('''
            CREATE INDEX IF NOT EXISTS idx_config_name ON config(name)
        ''').close()

def main(root):
    logging.debug('Main')
    sonosList = SonosList(root)
    sonosList.mainloop()
    sonosList.destroy()

if __name__ == '__main__':
    logging.info('Using data dir: "%s"', USER_DATA)
    
    root = tk.Tk()
    try:
        root.wm_title('SoCo')
        root.minsize(800,400)
        main(root)
##    except:
##        logging.debug(traceback.format_exc())
    finally:
        root.quit()
        root.destroy()
