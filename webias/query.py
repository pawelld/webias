# Copyright 2013 Pawel Daniluk, Bartek Wilczynski
#
# This file is part of WeBIAS.
#
# WeBIAS is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# WeBIAS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with WeBIAS. If not, see
# <http://www.gnu.org/licenses/>.


import webias.gnosis.xml.objectify as objectify
from genshi.template import NewTextTemplate


class XMLTree():
    def __init__(self, xml_string):
        self.tree=objectify.make_instance(xml_string, p=objectify.DOM)

        for e in objectify.walk_xo(self.tree):
            try:
                e.type
            except:
                e.type='value'

    def path(self, o):
        all=list(objectify.walk_xo(self.tree))

        if o not in all:
            raise Exception('Object not in query tree')

        res=''

        par=objectify.parent(o)

        if(par != self.tree):
            res=self.path(par) + '/'

        res+=objectify.tagname(o)

        return res

    def _get(self, tree, idx, *kwds):
        if kwds==():
            return tree
        else:
            l=kwds[0]
            try:
                (name, nidx)=l.split(':')
            except:
                (name, nidx)=(l,None)

            subtree=tree.__dict__[name]

            if idx!=None:
                try:
                    i=iter(subtree)
                except:
                    i=iter([subtree])

                subtree=None

                for t in i:
                    if t.index==idx:
                        subtree=t
                        break

            return self._get(subtree, nidx, *kwds[1:])

    def index_set(self, path):
        el=self.get(path)

        if el==None:
            return []

        res=list(set([t.index for t in objectify.children(el)]))

        res.sort()

        return res

    def get_search_prefix(self):
        try:
            return self.search_prefixes[-1]
        except:
            return ''

    def push_search_prefix(self, pref):
        sp=self.get_search_prefix()

        try:
            self.search_prefixes.append(sp+pref)
        except:
            self.search_prefixes=[sp+pref]

    def pop_search_prefix(self):
        try:
            self.search_prefixes.pop()
        except:
            pass

    def clear_search_prefix(self):
        self.search_prefixes=[]


    def get(self, path):
        try:
            prefix=self.get_search_prefix()
        except:
            prefix=''

        try:
            return self._get(self.tree, None, *(prefix+path).split('/'))
        except:
            return None

    def walk(self):
        for c in objectify.children(self.tree):
#            if objectify.tagname(c)=="BIAS_email":
#                continue

            prev=c
            par=c
            depth=1
            for o in objectify.walk_xo(c):
                if o!=c:
                    if objectify.parent(o) == prev:
                        depth+=1
                        par=prev
                    elif objectify.parent(o) != par:
                        depth-=1
                        par=objectify.parent(o)

                    prev=o

                yield (depth, o)


class Query(XMLTree):
    def make_command(self, template):
        return NewTextTemplate(template).generate(**self.tree.__dict__).render('text').strip()

    def walk(self):
        for (d,o) in XMLTree.walk(self):
            if objectify.tagname(o)=="BIAS_email":
                continue

            yield (d, o)

class Result(XMLTree):
    pass

