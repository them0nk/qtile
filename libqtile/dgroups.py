import itertools
import gobject

import libqtile.hook
from libqtile.config import Key
from libqtile.command import lazy

def simple_key_binder(mod, keynames=None):
    """
        Bind keys to mod+group position or to the keys specified as
        second argument.
    """
    def func(dgroup):
        # unbind all
        for key in dgroup.keys[:]:
            dgroup.qtile.unmapKey(key)
            dgroup.keys.remove(key)

        if keynames:
            keys = keynames
        else:
            # keys 1 to 9 and 0
            keys = map(str, range(1, 10) + [0])

        # bind all keys
        for keyname, group in zip(keys, dgroup.qtile.groups):
            name = group.name
            key = Key([mod], keyname, lazy.group[name].toscreen())
            key_s = Key([mod, "shift"], keyname, lazy.window.togroup(name))
            key_c = Key([mod, "control"], keyname,
                    lazy.group.switch_groups(name))
            dgroup.keys.append(key)
            dgroup.keys.append(key_s)
            dgroup.keys.append(key_c)
            dgroup.qtile.mapKey(key)
            dgroup.qtile.mapKey(key_s)
            dgroup.qtile.mapKey(key_c)

    return func

class Rule(object):
    """ A Rule contains a Match object, and a specification about what to do
    when that object is matched. """
    def __init__(self, match, group=None, float=False, intrusive=False):
        """
        :param match: ``Match`` object associated with this ``Rule``
        :param float: auto float this window?
        :param intrusive: override the group's exclusive setting?
        """
        self.match = match
        self.group = group
        self.float = float
        self.intrusive = intrusive

    def matches(self, w):
        return self.match.compare(w)

class DGroups(object):
    ''' Dynamic Groups '''
    def __init__(self, qtile, dgroups, key_binder=None, delay=1):
        self.qtile = qtile

        self.groups = dgroups
        self.groupMap = {}
        for group in self.groups:
            self.groupMap[group.name] = group

        self.rules = list(itertools.chain.from_iterable([g.rules for g in dgroups]))

        for group in dgroups:
            rules = [Rule(m, group=group.name) for m in group.matches]
            self.rules.extend(rules)

        self.keys = []

        self.key_binder = key_binder

        self._setup_hooks()
        self._setup_groups()

        self.delay = delay

        self.timeout = {}

    def _setup_groups(self):
        for group in self.groups:
            if group.init:
                self.qtile.addGroup(group.name)

            if group.spawn and not self.qtile.no_spawn:
                self.qtile.cmd_spawn(group.spawn)

    def _setup_hooks(self):
        libqtile.hook.subscribe.client_new(self._add)
        libqtile.hook.subscribe.client_killed(self._del)
        if self.key_binder:
            libqtile.hook.subscribe.setgroup(
                    lambda: self.key_binder(self))
            libqtile.hook.subscribe.addgroup(
                    lambda: self.key_binder(self))
            libqtile.hook.subscribe.delgroup(
                    lambda: self.key_binder(self))

    def shuffle_groups(self, lst, match):
        masters = []
        for client in lst:
            if match.compare(client):
                masters.append(client)
        for master in masters:
            lst.remove(master)
            lst.insert(0, master)

    def _add(self, client):
        if client in self.timeout:
            self.qtile.log.info('Remove dgroup source')
            gobject.source_remove(self.timeout[client])
            del(self.timeout[client])

        # ignore static windows
        if client.defunct:
            return

        group_set = False
        intrusive = False

        for rule in self.rules:
            # Matching Rules
            if rule.matches(client):
                if rule.group:
                    group_added = self.qtile.addGroup(rule.group)
                    client.togroup(rule.group)

                    group_set = True

                    group_obj = self.qtile.groupMap[rule.group]
                    group = self.groupMap.get(rule.group)
                    if group:
                        if group_added:
                            layout = group.layout
                            ratio = group.ratio
                            if layout:
                                group_obj.layout = layout
                            if ratio:
                                group_obj.ratio = ratio
                        master = group.master
                        if master:
                            group_obj.layout.shuffle(
                                   lambda lst: self.shuffle_groups(
                                       lst, master))

                if rule.float:
                    client.enablefloating()

                if rule.intrusive:
                    intrusive = group.intrusive

        # If app doesn't have a group
        if not group_set:
            current_group = self.qtile.currentGroup.name
            if current_group in self.groups and\
                    self.groupMap[current_group].exclusive and\
                    not intrusive:

                wm_class = client.window.get_wm_class()

                if wm_class:
                    if len(wm_class) > 1:
                        wm_class = wm_class[1]
                    else:
                        wm_class = wm_class[0]

                    group_name = wm_class
                else:
                    group_name = client.name
                    if not group_name:
                        group_name = "Unnamed"

                self.qtile.addGroup(group_name)
                client.togroup(group_name)

    def _del(self, client):
        group = client.group

        def delete_client():
            # Delete group if empty and dont persist
            if group and \
               self.groupMap[group.name] in self.groups and \
               not self.groupMap[group.name].persist and \
               len(group.windows) <= 0:
                self.qtile.delGroup(group.name)

        # wait the delay until really delete the group
        self.qtile.log.info('Add dgroup timer')
        self.timeout[client] = gobject.timeout_add_seconds(self.delay,
                                                         delete_client)
