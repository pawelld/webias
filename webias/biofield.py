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


import tempfile,subprocess,os
import webias.gnosis.xml.objectify as objectify
#import WeBIAS
import cherrypy
import data
import util

import Bio.PDB

import auth

import field

import biodb

class FieldPDBStructureValue(field.FieldGroupValue):
    def __init__(self, fld):
        field.FieldGroupValue.__init__(self, fld)
        self._type='PDBStructure'

    def _printValue(self):
        return self._children[0]._printValue()

    def _getAttributes(self):
        return self._children[0]._getAttributes()



class FieldPDBFileValue(field.FieldFileValue):
    def __init__(self, fld):
        field.FieldFileValue.__init__(self, fld)
        self._type='PDBStructure'

    def _getAttributes(self):
        val=self._getValue()

        return 'filename="%s"' % (val.filename)

    def _store(self, session, req):
        f=self._getValue().file

        if self._parent != None and self._parent._type=='PDBStructure':
            path=self._parent._getPath()
        else:
            path=self._getPath()

        file=data.File(request=req, path=path, name=self._getValue().filename, data=f.read(), type='input')
        f.seek(0)
        session.add(file)

class FieldStructureCodeValue(FieldPDBFileValue):
    def _printValue(self):
        return self._getValue().code


    def _getAttributes(self):
        val=self._getValue()

        return 'code="%s" db="%s" filename="%s"' % (val.code, val.db, val.filename)


class StructureCode(field.Text):
    valueClass=FieldStructureCodeValue
    availabledbs={'SCOP': biodb.SCOPHandler(), 'PDB': biodb.PDBHandler()}

    def get_templates(self):
        return ['system/form/bioform.genshi']

    def assign_value(self, valid, kwds):
        if valid=='VALID' or valid=='WARNING':
            code=self.getValue(kwds)

            val=util.expando()

            db=self.getDB(code)
            handler=self.availabledbs[db]

            val.code=code
            val.db=db
            val.file=handler.getFile(code)
            val.filename=os.path.basename(val.file.name)

            res=self.valueClass(self)
            res._value=val

            return res


        return None

    def getDefault(self, query=None):
        try:
            def_val=self.default
        except:
            def_val=""

        if query!=None:
            if objectify.parent(self).__class__==PDBStructure:
                formname=objectify.parent(self).getFormName()
            else:
                formname=self.getFormName()

            n=query.get(formname)
            if n!=None and n.type == 'PDBStructure' and hasattr(n, 'db'):
                def_val=n.PCDATA

        return def_val


    def getDB(self, val):
        # print val
        for db in self.dblist:
            try:
                self.availabledbs[db].getFile(val)
                return db
            except biodb.InvalidID:
                pass

        return None

    def check_value(self,val):
        if self.getDB(val) != None:
            return 'VALID', []

        return 'INVALID',[field.Message('INVALID', self, "Parameter %s is not a valid structure code."% self.info)]

class PDBFile(field.File):
    valueClass=FieldPDBFileValue


    def getDefault(self, query=None):
        if query!=None:
            if objectify.parent(self).__class__==PDBStructure:
                formname=objectify.parent(self).getFormName()
            else:
                formname=self.getFormName()

            n=query.get(formname)
            # print n, n.type, hasattr(n, 'db')
            if n!=None and n.type == 'PDBStructure' and not hasattr(n, 'db'):
                f=query.req.get_file(formname, n.PCDATA)
                # print formname, f
                return f

        return None


    def get_templates(self):
        return ['system/form/bioform.genshi']

    def check_file(self,fieldstorage):

        p=Bio.PDB.PDBParser(PERMISSIVE=False)

        self.valid='VALID'

        try:
            s=p.get_structure('mol', fieldstorage.file)
        except Exception as e:
            return 'INVALID',[field.Message('INVALID', self, "Problem with %s: %s\n"%(self.info,e.message))]
        finally:
            fieldstorage.file.seek(0)

        return 'VALID', []


class PDBStructure(field.Group):
    valueClass=FieldPDBStructureValue

    def create_content(self):
        self.grouptype="XOR"

        sources=getattr(self, 'source', "PDB, SCOP, file")

        srclist=[x.strip() for x in sources.split(',')]
        dblist=[x for x in srclist if x != 'file']

        self.content=[]

        if len(dblist)>0:
            scode=StructureCode()
            scode.id="name"
            scode.name="Insert structure code ("+' or '.join(dblist)+")"
            scode.tip="insert structure code ("+' or '.join(dblist)+" format)"
            scode.info=self.info+" code"
            scode.optional="yes"
            scode.dblist=dblist
            scode.__parent__=self
            scode._seq=[]
            self.content.append(scode)


        if 'file' in srclist:
            pfile=PDBFile()
            pfile.id="file"
            if self.content != []:
                pfile.name=" or upload structure file"
            else:
                pfile.name="Upload structure file"

            pfile.info=self.info+" file"
            pfile.optional="yes"
            pfile.tip="upload structure file"

            self.content.append(pfile)

            pfile.__parent__=self
            pfile._seq=[]


        self._seq=self.content


    def children(self):
        if not hasattr(self, 'content'):
            self.create_content()

        return self.content

    def process_parameters(self, kwds):
        (valid, messages, values)=field.Group.process_parameters(self, kwds)

        return valid, messages, values


objectify._XO_structurecode=StructureCode
objectify._XO_pdbfile=PDBFile
objectify._XO_pdbstructure=PDBStructure
