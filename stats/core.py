#
# core.py
#
# Copyright (C) 2009 Ian Martin <ianmartin@cantab.net>
# Copyright (C) 2008 Damien Churchill <damoxc@gmail.com>
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
# Copyright (C) Marcos Pinto 2007 <markybob@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA    02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception

import time

import deluge
from deluge.log import LOG as log
from deluge.plugins.corepluginbase import CorePluginBase
from deluge import component
from deluge import configmanager
import gobject

#from deluge.plugins.coreclient import client #1.1 and later only
#client: see http://dev.deluge-torrent.org/wiki/Development/UiClient#Remoteapi

DEFAULT_PREFS = {
    "test":"NiNiNi",
    "update_interval":1000, #1 seconds.
    "length":150, # 2 seconds * 150 --> 5 minutes.
}

DEFAULT_TOTALS = {
    "total_upload":0,
    "total_download":0,
    "total_payload_upload":0,
    "total_payload_download":0,
    "stats":{}
}

def get_key(config, key):
    try:
        return config[key]
    except KeyError:
        return None

def mean(items):
    try:
        return sum(items)/ len(items)
    except Exception:
        return 0

class Core(CorePluginBase):
    totals = {} #class var to catch only updating this once per session in enable.

    def enable(self):
        log.debug("Stats plugin enabled")
        self.core = component.get("Core")
        self.stats ={}
        self.count = {}
        self.intervals = [1, 5, 30, 300]
      
        self.last_update = {}
        t = time.time()
        for i in self.intervals:
            self.stats[i] = {}
            self.last_update[i] = t
            self.count[i] = 0
        

        self.config = configmanager.ConfigManager("stats.conf", DEFAULT_PREFS)
        self.saved_stats = configmanager.ConfigManager("stats.totals", DEFAULT_TOTALS)
        if self.totals == {}:
            self.totals.update(self.saved_stats.config)

        #self.stats = get_key(self.saved_stats, "stats") or {}
        self.add_stats(
            'upload_rate',
            'download_rate',
            'num_connections',
            'dht_nodes',
            'dht_cache_nodes',
            'dht_torrents',
            'num_peers',
        )

        #update interval needs to be at least as rapid as min interval...
        self.update_timer = gobject.timeout_add(
            self.config["update_interval"], self.update_stats)
        self.save_timer = gobject.timeout_add(60 * 1000, self.save_stats)
        self.length = self.config["length"]
        self.update_stats()

    def disable(self):
        self.save_stats()
        gobject.source_remove(self.update_timer)
        gobject.source_remove(self.save_timer)

    def add_stats(self, *stats):
        for stat in stats:
            for i in self.intervals:
                if stat not in self.stats[i]:
                    self.stats[i][stat] = []
          

    def update_stats(self):
        try:
            #Get all possible stats!
            stats = self.core.export_get_stats()
            status = self.core.session.status()
            for stat in dir(status):
                if not stat.startswith('_') and stat not in stats:
                    stats[stat] = getattr(status, stat, None)

            update_time = time.time()
            self.last_update[1] = update_time
            #extract the ones we are interested in
            #adding them to the 1s array
            for stat, stat_list in self.stats[1].iteritems():
                if stat in stats:
                    stat_list.insert(0, int(stats[stat]))
                else:
                    stat_list.insert(0, 0)
                if len(stat_list) > self.length:
                    stat_list.pop()
                    
            def update_interval(interval, base, multiplier):
                self.count[interval] = self.count[interval] + 1
                if self.count[interval] >= interval:
                    self.last_update[interval] = update_time
                    self.count[interval] =  0
                    current_stats = self.stats[interval]
                    for stat, stat_list in self.stats[base].iteritems():
                        try:
                            avg = mean(stat_list[0:multiplier])
                        except ValueError:
                            avg = 0
                        current_stats[stat].insert(0, avg)
                        if len(current_stats[stat]) > self.length:
                            current_stats[stat].pop()

            update_interval(5, 1, 5)
            update_interval(30, 5, 6)
            update_interval(300, 30, 10)

        except Exception, e:
            log.error("Stats update error %s" % e)
        return True

    def save_stats(self):
        try:
            self.saved_stats["stats"] = self.stats
            for key, value in self.export_get_totals().iteritems():
                self.saved_stats.config[key] = value              
            self.saved_stats.save()
        except Exception, e:
            log.error("Stats save error", e)
        return True


    # export:
    def export_get_stats(self, keys, interval):
      
        if interval not in self.intervals:
            return None

        stats_dict = {}
        for stat in self.stats[interval]:
            if stat not in keys:
                continue
            stats_dict[stat] = self.stats[interval][stat]
          
        stats_dict["_last_update"] = self.last_update[interval]
        stats_dict["_length"] = self.config["length"]
        stats_dict["_update_interval"] = interval
        return stats_dict

    def export_get_totals(self):
        result = {}
        session_totals = self.export_get_session_totals()
        for key in session_totals:
            result[key] = self.totals[key] + session_totals[key]
        return result

    def export_get_session_totals(self):
        status = self.core.session.status()
        return {
            "total_upload":status.total_upload,
            "total_download":status.total_download,
            "total_payload_upload":status.total_payload_upload,
            "total_payload_download":status.total_payload_download
        }

    def export_set_config(self, config):
        "sets the config dictionary"
        for key in config.keys():
            self.config[key] = config[key]
        self.config.save()

    def export_get_config(self):
        "returns the config dictionary"
        return self.config.config

    def export_get_intervals(self):
        "Returns the available resolutions"
        return self.intervals
