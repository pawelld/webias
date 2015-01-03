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

import auth

#from WeBIAS import get_db_conn


class Message():
    def __init__(self, valid, field, message):
        self.valid=valid
        self.field=field
        self.message=message

class FieldValue():
    def __init__(self, field):
        self._field=field
        self._parent=None

    def _getId(self):
        return self._field.id

    def _store(self, session, req):
        pass

    def _getPath(self):
        res=''

        if self._parent != None:
            res=self._parent._getPath()

        if res != '':
            res+='/'

        res+=self._getId()

        try:
            idx=self.idx
            res+='/'+str(idx)
        except:
            pass

        return res

    def _printValue(self):
        return self._getValue()

    def _getAttributes(self):
        return ''

    def _makeXML(self):
        t=''
        idx=''

        if self._type!=None:
            t='type="%s"'%self._type

        try:
            idx='index="%d"'%self.idx
        except:
            pass

        return '<%s %s %s %s>%s</%s>'%(self._getId(), t, idx, self._getAttributes(), self._printValue(), self._getId())

class FieldSingleValue(FieldValue):
    def __init__(self, field):
        FieldValue.__init__(self, field)
        self._type='value'

    def _getValue(self):
        try:
            return self._value
        except NameError:
            return ""



class FieldFileValue(FieldSingleValue):
    def __init__(self, field):
        FieldSingleValue.__init__(self, field)
        self._type='file'

    def _printValue(self):
        return self._getValue().filename

    def _store(self, session, req):
        f=self._getValue().file

        file=data.File(request=req, path=self._getPath(), name=self._getValue().filename, data=f.read(), type='input')
        f.seek(0)
        session.add(file)



class FieldGroupValue(FieldValue):
    def __init__(self, field):
        FieldValue.__init__(self, field)
        self._children=[]
        self._type='group'

    def _addChild(self, c):
        id=c._getId()
        self.__dict__[id]=c
        self._children.append(c)
        c._parent=self

    def _printValue(self):
        res=''
        for c in self._children:
            res+=c._makeXML()
        return res

    def _store(self, session, req):
        for c in self._children:
            c._store(session, req)

class FormValues(FieldGroupValue):
    def __init__(self):
        FieldGroupValue.__init__(self, None)
        self._type=None

    def _getId(self):
        return 'query'

    def _getPath(self):
        return ''


class Parameters(objectify._XO_):
    valueClass=FormValues

    def get_templates(self):
        res=[]

        for c in self.children():
            for f in objectify.walk_xo(c):
                if hasattr(f, 'get_templates'):
                    res+=f.get_templates()

        return set(res)


    def children(self):
        return objectify.children(self)


    def _getFormNameRec(self):
        return ''

    def process_parameters(self, kwds):
        valid='VALID'
        messages=[]
        res=self.valueClass()
        for par in self.children():
            v, msg, val=par.process_parameters(kwds)

            messages.extend(msg)

            if val:
                res._addChild(val)

            if v=='WARNING' and valid=='VALID' or v=='INVALID':
                valid=v

        return valid, messages, res


class Field(objectify._XO_):
    valueClass=FieldSingleValue

    def children(self):
        return objectify.children(self)

    def app(self):
        a=self
        while objectify.tagname(a)!='Application':
            a=objectify.parent(a)

        return a

    def getPath(self):
        a=self
        res=[]
        while isinstance(a, Field):
            res.append(a.id)
            a=objectify.parent(a)

        res.reverse()
        return '/'.join(res)

    def getDefault(self, query=None):
        try:
            def_val=self.default
        except:
            def_val=""

        if query!=None:
            n=query.get(self.getFormName())
            if n!=None and n.type == 'value':
                def_val=n.PCDATA


        return def_val

    def getValue(self, kwds):
        try:
            data=kwds[self.getFormName()]
        except:
            data=""

        return data

    def isOptional(self):
        try:
            optional=self.optional
        except:
            optional="no"

        if optional=="yes" or optional=="Yes" or optional=="1":
            return True
        else:
            return False

    def _getFormNameRec(self):
        return self.getFormName()

    def getFormName(self):

        name=''

        try:
            parent_name=objectify.parent(self)._getFormNameRec()
            if parent_name != '':
                name=parent_name+'/'
        except:
            pass

        name+=self.id

        return name

    def validate(self, kwds):
        if self.getValue(kwds) == "":
            if self.isOptional():
                return 'EMPTY', []
            else:
                return 'INVALID', [Message('INVALID', self, "Parameter %s is missing!"%self.info)]
        else:
            return self.check_value(self.getValue(kwds))


    def assign_value(self, valid, kwds):
        if valid=='VALID' or valid=='WARNING':
            res=self.valueClass(self)
            res._value=self.getValue(kwds)
        else:
            res=None

        return res

    def check_value(self, val):
        return 'VALID', []

    def process_parameters(self, kwds):
        valid, message=self.validate(kwds)
        return valid, message, self.assign_value(valid, kwds)




class Integer(Field):
    def check_value(self,val):
        try:
            x=int(val)
            return 'VALID', []
        except ValueError:
            return 'INVALID', [Message('INVALID', self, "Parameter %s should be an integer."%self.info)]


class Float(Field):
    def check_value(self,val):
        try:
            x=float(val)
            return 'VALID', []
        except ValueError:
            return 'INVALID', [Message('INVALID', self, "Parameter %s should be an decimal number."%self.info)]


class Text(Field):
    def check_value(self,val):
        if str(val).isalnum():
            return 'VALID', []
        else:
            return 'INVALID', [Message('INVALID', self, "Parameter %s should be alphanumeric."%self.info)]


class Email(Text):
    def __init__(self):
        self.id="BIAS_email"
        self.name="Your e-mail address"
        self.info="e-mail address"
        self.optional="yes"

    def getDefault(self, query=None):
        if auth.get_login()!=None:
            usr=data.User.get_by_login(cherrypy.request.db, auth.get_login())

            return usr.e_mail
        else:
            return Text.getDefault(self, query=None)

    def check_value(self,val):
        try:
            for letter in val:
                if letter not in ("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ@._-"):
                    raise ValueError
            split_at=val.split("@")
            if len(split_at)!=2:
               raise ValueError
            split_dot=split_at[1].split(".")
            if len(split_dot)<2:
                raise ValueError
            return 'VALID', []
        except ValueError:
            return 'INVALID', [Message('INVALID', self, "Parameter %s should be an e-mail address."%self.info)]


class Section(Field):
    def validate(self,kwds):
        return 'IGNORE', []


class Checkbox(Field):
    def getValue(self, kwds):
        try:
            data=kwds[self.getFormName()]
            data=True
        except:
            data=False

        return data

    def validate(self,kwds):
        if not self.getValue(kwds) and self.isOptional():
            return 'EMPTY', []

        return 'VALID', []


class File(Field):
    valueClass=FieldFileValue

    def getValue(self, kwds):
        try:
            id=kwds[self.getFormName()+'/old']

            val=util.expando()
            session=cherrypy.request.db

            import StringIO
            file=session.query(data.File).get(id)
            val.file=StringIO.StringIO(file.data)
            val.filename=file.name
        except KeyError:
            val=Field.getValue(self,kwds)
        return val

    def validate(self, kwds):
        # print self.getFormName()
        # print kwds
        # print self.getValue(kwds)
        if self.getValue(kwds)=='' or self.getValue(kwds).filename == "":
            if self.isOptional():
                return 'EMPTY', []
            else:
                return 'INVALID', [Message('INVALID', self, "Parameter %s is missing!"%self.info)]
        else:
            return self.check_file(self.getValue(kwds))

    def check_file(self, file):
        return 'VALID', []

    def getDefault(self, query=None):
        if query!=None:
            n=query.get(self.getFormName())
            if n!=None and n.type == 'file':
                f=query.req.get_file(self.getFormName(), n.PCDATA)
                return f

        return None



class Select(Field):
    def check_value(self,val):
        try:
            sel=int(val)
            for opt in self.option:
                if sel==int(opt.value):
                    return 'VALID', []

            return 'INVALID', [Message('INVALID', self, "Parameter %s - invalid option value."%self.info)]
        except ValueError:
            return 'INVALID', [Message('INVALID', self, "Parameter %s - option value should be integer."%self.info)]

class Group(Field):
    valueClass=FieldGroupValue

    def getInfo(self):
        res=""
        for par in self.children():
            try:
                if res=="":
                    res=par.info
                else:
                    res=res+", "+par.info
            except:
                pass

        return res

    def assign_value(self, kwds):
        raise NotImplementedError

    def process_parameters(self, kwds):
        nval=nemp=ninv=0
        messages=[]
        res=self.valueClass(self)
        for par in self.children():
            v, msg, val=par.process_parameters(kwds)

            messages.extend(msg)

            if val:
                nval+=1
                res._addChild(val)
            elif v=="EMPTY":
                nemp+=1
            elif v=="INVALID":
                ninv+=1

        ngroup=nval+nemp+ninv

        valid='VALID'

        if ninv>0:
            valid='INVALID'
        elif self.isOptional() and nval==0:
            valid='EMPTY'
        elif self.grouptype=="AND":
            if self.isOptional():
                if nval!=ngroup and nemp!=ngroup:
                    valid='INVALID'
                    messages.append(Message('INVALID', self, "Please provide data for <b>all</b> of the folowing parameters or leave <b>all</b> fields blank: %s\n"%self.getInfo()))
            else:
                if nval!=ngroup:
                    valid='INVALID'
                    messages.append(Message('INVALID', self, "Please provide data for <b>all</b> of the folowing parameters: %s"%self.getInfo()))

        elif self.grouptype=="XOR":
            if self.isOptional():
                if nval>1:
                    valid='INVALID'
                    messages.append(Message('INVALID', self, "Please provide data for <b>exactly one</b> of the folowing parameters or leave all fields blank: %s"%self.getInfo()))
            else:
                if nval!=1:
                    valid='INVALID'
                    messages.append(Message('INVALID', self, "Please provide data for <b>exactly one</b> of the folowing parameters: %s"%self.getInfo()))
        elif self.grouptype=="OR":
            if nemp==ngroup:
                valid='INVALID'
                messages.append(Message('INVALID', self, "Please provide data for <b>at least one</b> of the folowing parameters: %s"%self.getInfo()))

        if valid!='VALID':
            res=None

        return valid, messages, res

class VarGroup(Field):
    valueClass=FieldGroupValue

    def getMax(self):
        try:
            return self.max
        except:
            return 0

    def getMin(self):
        try:
            return self.min
        except:
            return 0

    def _getFormNameRec(self):
        return ''

    def assign_value(self, kwds):
        raise NotImplementedError

    def process_parameters(self, kwds):
        nval=nemp=ninv=0
        messages=[]
        res=self.valueClass(self)

        name=self.getFormName()+':'

        prefixes=list(set([key.replace(name,'',1).split('/')[0]+'/' for key in kwds.keys() if key.startswith(name)]))
        prefixes.sort()

        prefixes=[name+p for p in prefixes]

        idx=1

        for p in prefixes:
            selkwds=dict((key.replace(p,'',1),val) for (key,val) in kwds.items() if key.startswith(p))

            elnval=elnemp=elninv=0

            for par in self.children():
                v, msg, val=par.process_parameters(selkwds)

                messages.extend(msg)

                if val:
                    elnval+=1
                    val.idx=idx
                    res._addChild(val)
                elif v=="EMPTY":
                    elnemp+=1
                elif v=="INVALID":
                    elninv+=1

            if elninv>0:
                ninv+=1
            elif elnval+elninv==0:
                nemp+=1
            else:
                nval+=1

#            res._addChild(el)
            idx+=1


        ngroup=nval+nemp+ninv

        valid='VALID'

        if ninv>0:
            valid='INVALID'
        elif self.isOptional() and ngroup==0:
            valid='EMPTY'
        elif nemp>0:
            valid='INVALID'
            messages.append(Message('INVALID', self, "Please provide data for <b>all</b> instances of %s.\n"%self.info))
        elif nval<int(self.min):
            valid='INVALID'
            messages.append(Message('INVALID', self, "Please provide data for <b>at least %s</b> instances of %s.\n"%(self.min,self.info)))
        elif nval>int(self.max):
            valid='INVALID'
            messages.append(Message('INVALID', self, "Please provide data for <b>no more than %s</b> instances of %s.\n"%(self.max,self.info)))

        if valid!='VALID':
            res=None

        return valid, messages, res

def objectify_clean():
# Ugly hack to call after parsing app definitions.
    for key in objectify.__dict__.keys():
        if key[0:4]=='_XO_' and len(key)>4:
            del objectify.__dict__[key]

objectify._XO_parameters=Parameters
objectify._XO_integer=Integer
objectify._XO_float=Float
objectify._XO_text=Text
objectify._XO_email=Email
objectify._XO_section=Section
objectify._XO_checkbox=Checkbox
objectify._XO_file=File
objectify._XO_select=Select
objectify._XO_group=Group
objectify._XO_vargroup=VarGroup
