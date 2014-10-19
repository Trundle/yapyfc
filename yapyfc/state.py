from gi.repository import Gio

class Session(object):
    def __init__(self, local_path):
        self.local = Gio.file_new_for_path(local_path)
        self.remote = None