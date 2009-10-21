#
# gtkui.py
#
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
#
# Basic plugin template created by:
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
# Copyright (C) 2007, 2008 Andrew Resch <andrewresch@gmail.com>
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

# It should be noted that torrentdetails.add_tab() cannot be used
# On exit the position of all displayed tabs is saved in tabs.state
# then on restart TorrentDetails tries to lookup default_tabs["Graphs"]
# and deluge exits with a key exception

import gtk
import gobject
from gtk.glade import XML

import graph
from deluge import component
from deluge.log import LOG as log
from deluge.common import fspeed
from deluge.ui.client import aclient
from deluge.ui.gtkui.torrentdetails import Tab

def neat_time(column, cell, model, iter):
    """Render seconds as seconds or minutes with label"""
    seconds = model.get_value(iter, 0)
    if seconds >60:
        text = "%d %s" % (seconds / 60, _("minutes"))
    elif seconds == 60:
        text = _("1 minute")
    elif seconds == 1:
        text = _("1 second")
    else:
        text = "%d %s" % (seconds, _("seconds"))
    cell.set_property('text', text)
    return

def int_str(number):
    return (str(int(number)))


class GraphsTab(Tab):
    def __init__(self, glade):
        Tab.__init__(self)
        self.glade = glade
        self.window = self.glade.get_widget('graph_tab')
        self.notebook = self.glade.get_widget('graph_notebook')
        self.notebook.connect("switch-page", self._on_notebook_switch_page)
        self.label = self.glade.get_widget('graph_label')

        self._name = 'Graphs'
        self._child_widget = self.window
        self._tab_label = self.label
        self.bandwidth_graph = self.glade.get_widget('bandwidth_graph')
        self.bandwidth_graph.connect('expose_event', self.graph_expose)

        self.connections_graph = self.glade.get_widget('connections_graph')
        self.connections_graph.connect('expose_event', self.graph_expose)

        self.seeds_graph = self.glade.get_widget('seeds_graph')
        self.seeds_graph.connect('expose_event', self.graph_expose)

        self.selected_interval = 1 #should come from config or similar
        self.select_bandwidth_graph()

        self.window.unparent()
        self.label.unparent()

        self.update_timer = None

        self.selected_interval = 0
        self.intervals = None
        self.intervals_combo = self.glade.get_widget('combo_intervals')
        cell = gtk.CellRendererText()
        self.intervals_combo.pack_start(cell, True)
        self.intervals_combo.set_cell_data_func(cell, neat_time)
        self.intervals_combo.connect("changed", self._on_selected_interval_changed)


    def start(self):
        log.debug("Graph tab starting")
        self.update_graph()
        #this must follow update_graph else the force_call makes things co crazy
        self.update_intervals()
        self.update_timer = gobject.timeout_add(1000, self.update_graph)

    def stop(self):
        if self.update_timer is not None:
            gobject.source_remove(self.update_timer)
     
    def graph_expose(self, widget, event):
        context = self.graph_widget.window.cairo_create()
        # set a clip region
        context.rectangle(event.area.x, event.area.y,
                           event.area.width, event.area.height)
        context.clip()
        self.graph.draw_to_context(context,
                                   self.graph_widget.allocation.width,
                                   self.graph_widget.allocation.height)
        #Do not propagate the event
        return False

    def update_graph(self):
        self.graph.async_request()
        aclient.force_call(True)
        self.graph_widget.queue_draw()
        return True

    def update_intervals(self):
        aclient.stats_get_intervals(self._on_intervals_changed)

    def select_bandwidth_graph(self):
        log.debug("Selecting bandwidth graph")
        self.graph_widget =  self.bandwidth_graph
        self.graph = graph.Graph()
        self.graph.add_stat('download_rate', label='Download Rate', color=graph.green)
        self.graph.add_stat('upload_rate', label='Upload Rate', color=graph.blue)
        self.graph.set_left_axis(formatter=fspeed, min=10240)
        self.graph.set_interval(self.selected_interval)


    def select_connections_graph(self):
        log.debug("Selecting connections graph")
        self.graph_widget =  self.connections_graph
        g = graph.Graph()
        self.graph = g
        g.add_stat('dht_nodes', color=graph.orange)
        g.add_stat('dht_cache_nodes', color=graph.blue)
        g.add_stat('dht_torrents', color=graph.green)
        g.add_stat('num_connections', color=graph.darkred) #testing : non dht
        g.set_left_axis(formatter=int_str, min=10)
        self.graph.set_interval(self.selected_interval)

    def select_seeds_graph(self):
        log.debug("Selecting connections graph")
        self.graph_widget =  self.seeds_graph
        self.graph = graph.Graph()
        self.graph.add_stat('num_peers', color=graph.blue)
        self.graph.set_left_axis(formatter=int_str, min=10)
        self.graph.set_interval(self.selected_interval)


    def _on_intervals_changed(self, intervals):
        liststore = gtk.ListStore(int)
        for inter in intervals:
            liststore.append([inter])
        self.intervals_combo.set_model(liststore)
        try:
            current = intervals.index(self.selected_interval)
        except:
            current = 0
        #should select the value saved in config
        self.intervals_combo.set_active(current)

    def _on_selected_interval_changed(self, combobox):
        model = combobox.get_model()
        iter = combobox.get_active_iter()
        self.selected_interval = model.get_value(iter, 0)
        self.graph.set_interval(self.selected_interval)
        self.update_graph()
        return True

    def _on_notebook_switch_page(self, notebook, page, page_num):
        p = notebook.get_nth_page(page_num)
        if p is self.bandwidth_graph:
            self.select_bandwidth_graph()
            self.update_graph()
        elif p is self.connections_graph:
            self.select_connections_graph()
            self.update_graph()
        elif p is self.seeds_graph:
            self.select_seeds_graph()
            self.update_graph()
        return True

class GtkUI(object):
    def __init__(self, plugin_api, plugin_name):
        log.debug("Calling Stats UI init")
        self.plugin = plugin_api

    def enable(self):
        self.glade = XML(self.get_resource("config.glade"))
        self.plugin.add_preferences_page("Stats", self.glade.get_widget("prefs_box"))
        self.plugin.register_hook("on_apply_prefs", self.on_apply_prefs)
        self.plugin.register_hook("on_show_prefs", self.on_show_prefs)
        self.on_show_prefs()

        self.graphs_tab = GraphsTab(XML(self.get_resource("tabs.glade")))
        self.torrent_details = component.get('TorrentDetails')
        self.torrent_details.notebook.append_page(self.graphs_tab.window, self.graphs_tab.label)
        self.notebook_signals = []
        self.notebook_signals.append(self.torrent_details.notebook.connect("switch-page", self._on_notebook_switch_page))
        self.notebook_signals.append(self.torrent_details.notebook.connect("hide", self._on_notebook_hide))
        self.notebook_signals.append(self.torrent_details.notebook.connect("show", self._on_notebook_show))


    def disable(self):
        for signal in self.notebook_signals:
            self.torrent_details.notebook.disconnect(signal)
        self.plugin.remove_preferences_page("Stats")
        self.plugin.deregister_hook("on_apply_prefs", self.on_apply_prefs)
        self.plugin.deregister_hook("on_show_prefs", self.on_show_prefs)
        # Remove the right hand tab, lets hope it's our one!
        self.graphs_tab.stop()
        self.torrent_details.notebook.remove_page(-1)
        del self.graphs_tab

    def on_apply_prefs(self):
        log.debug("applying prefs for Stats")
        config = {
            "test":self.glade.get_widget("txt_test").get_text()
        }
        aclient.stats_set_config(None, config)

    def on_show_prefs(self):
        aclient.stats_get_config(self.cb_get_config)

    def cb_get_config(self, config):
        "callback for on show_prefs"
        self.glade.get_widget("txt_test").set_text(config["test"])

    def get_resource(self, filename):
        import pkg_resources, os
        return pkg_resources.resource_filename("stats", os.path.join("data", filename))



    def _on_notebook_switch_page(self,notebook, page, page_num):
        if notebook.get_nth_page(page_num) is self.graphs_tab.window:
            self.graphs_tab.start()
        else:
            self.graphs_tab.stop()
        return True

    def _on_notebook_hide(self, widget):
        self.graphs_tab.stop()
        return True

    def _on_notebook_show(self, notebook):
        #annoyingly the torrentdetails behaviour is different when removing all tabs
        #It removes all tabs from the notebook when hiding itself, so we have to add
        #our tab back
        
        #check the graphs tab is displayed, if not add it
        if notebook.page_num(self.graphs_tab.window) is -1:
            notebook.append_page(self.graphs_tab.window, self.graphs_tab.label)
        return True
