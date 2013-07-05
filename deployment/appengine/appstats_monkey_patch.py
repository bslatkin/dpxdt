#!/usr/bin/env python
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Modified version of appstats variable formatting code.

Does not call __nonzero__ or __bool__ in user code, which breaks with
SQLAlchemy's ColumnElement class.

Original code:
  https://code.google.com/p/googleappengine/source/browse/trunk/python/google/appengine/ext/appstats/formatting.py
"""

from google.appengine.ext.appstats.formatting import *


def _format_value(val, limit, level, len=len, repr=repr):
    if level <= 0:
        return '...'

    typ = type(val)

    if typ in EASY_TYPES:
        if typ is float:
            rep = str(val)
        elif typ is long:
            if val >= 10L ** 99:
                return '...L'
            elif val <= -10L ** 98:
                return '-...L'
            else:
                rep = repr(val)
        else:
            rep = repr(val)
        if typ is long and len(rep) > limit:
            n1 = (limit - 3) // 2
            n2 = limit - 3 - n1
            rep = rep[:n1] + '...' + rep[-n2:]
        return rep

    if typ in META_TYPES:
        return val.__name__

    if typ in STRING_TYPES:
        n1 = (limit - 3) // 2
        if n1 < 1:
            n1 = 1
        n2 = limit - 3 - n1
        if n2 < 1:
            n2 = 1
        if len(val) > limit:
            rep = repr(val[:n1] + val[-n2:])
        else:
            rep = repr(val)
            if len(rep) <= limit:
                return rep
        return rep[:n1] + '...' + rep[-n2:]

    if typ is types.MethodType:
        if val.im_self is None:
            fmt = '<unbound method %s of %s>'
        else:
            fmt = '<method %s of %s<>>'
        if val.im_class is not None:
            return fmt % (val.__name__, val.im_class.__name__)
        else:
            return fmt % (val.__name__, '?')

    if typ is types.FunctionType:
        nam = val.__name__
        if nam == '<lambda>':
            return nam
        else:
            return '<function %s>' % val.__name__

    if typ is types.BuiltinFunctionType:
        if val.__self__ is not None:
            return '<built-in method %s of %s<>>' % (val.__name__,
                    type(val.__self__).__name__)
        else:
            return '<built-in function %s>' % val.__name__

    if typ is types.ModuleType:
        if hasattr(val, '__file__'):
            return '<module %s>' % val.__name__
        else:
            return '<built-in module %s>' % val.__name__

    if typ is types.CodeType:
        return '<code object %s>' % val.co_name

    if isinstance(val, ProtocolBuffer.ProtocolMessage):
        buf = [val.__class__.__name__, '<']
        limit -= len(buf[0]) + 2
        append = buf.append
        first = True

        dct = getattr(val, '__dict__', None)
        if dct:
            for (k, v) in sorted(dct.items()):
                if k.startswith('has_') or not k.endswith('_'):
                    continue
                name = k[:-1]

                has_method = getattr(val, 'has_' + name, None)
                if has_method is not None:

                    if type(has_method) is not types.MethodType \
                        or not has_method():
                        continue

                size_method = getattr(val, name + '_size', None)
                if size_method is not None:

                    if type(size_method) is not types.MethodType \
                        or not size_method():
                        continue

                if has_method is None and size_method is None:
                    continue

                if first:
                    first = False
                else:
                    append(', ')
                limit -= len(name) + 2
                if limit <= 0:
                    append('...')
                    break
                append(name)
                append('=')
                rep = _format_value(v, limit, level - 1)
                limit -= len(rep)
                append(rep)
        append('>')
        return ''.join(buf)

    dct = getattr(val, '__dict__', None)
    if type(dct) is dict:
        if typ is INSTANCE_TYPE:
            typ = val.__class__
        typnam = typ.__name__
        priv = '_' + typnam + '__'
        buffer = [typnam, '<']
        limit -= len(buffer[0]) + 2
        if len(dct) <= limit // 4:
            names = sorted(dct)
        else:
            names = list(dct)
        append = buffer.append
        first = True

        if issubclass(typ, BUILTIN_TYPES):

            for builtin_typ in BUILTIN_TYPES:
                if issubclass(typ, builtin_typ):
                    try:
                        val = builtin_typ(val)
                        assert type(val) is builtin_typ
                    except Exception:
                        break
                    else:
                        append(_format_value(val, limit, level - 1))
                        first = False
                        break

        for nam in names:
            if not isinstance(nam, basestring):
                continue
            if first:
                first = False
            else:
                append(', ')
            pnam = nam
            if pnam.startswith(priv):
                pnam = pnam[len(priv) - 2:]
            limit -= len(pnam) + 2
            if limit <= 0:
                append('...')
                break
            append(pnam)
            append('=')
            rep = _format_value(dct[nam], limit, level - 1)
            limit -= len(rep)
            append(rep)
        append('>')
        return ''.join(buffer)

    how = CONTAINER_TYPES.get(typ)
    if how:
        (head, tail) = how
        buffer = [head]
        append = buffer.append
        limit -= 2
        series = val
        isdict = typ is dict
        # This explodes with SQLAlchemy's ColumnElement class.
        # if isdict and len(val) <= limit // 4:
        #     series = sorted(val)
        try:
            for elem in series:
                if limit <= 0:
                    append('...')
                    break
                rep = _format_value(elem, limit, level - 1)
                limit -= len(rep) + 2
                append(rep)
                if isdict:
                    rep = _format_value(val[elem], limit, level - 1)
                    limit -= len(rep)
                    append(':')
                    append(rep)
                append(', ')
            if buffer[-1] == ', ':
                if tail == ')' and len(val) == 1:
                    buffer[-1] = ',)'
                else:
                    buffer[-1] = tail
            else:
                append(tail)
            return ''.join(buffer)
        except (RuntimeError, KeyError):

            return head + tail \
                + ' (Container modified during iteration)'

    if issubclass(typ, BUILTIN_TYPES):

        for builtin_typ in BUILTIN_TYPES:
            if issubclass(typ, builtin_typ):
                try:
                    val = builtin_typ(val)
                    assert type(val) is builtin_typ
                except Exception:
                    break
                else:
                    typnam = typ.__name__
                    limit -= len(typnam) + 2
                    return '%s<%s>' % (typnam, _format_value(val,
                            limit, level - 1))

    if message is not None and isinstance(val, message.Message):
        buffer = [typ.__name__, '<']
        limit -= len(buffer[0]) + 2
        append = buffer.append
        first = True
        fields = val.ListFields()

        for (f, v) in fields:
            if first:
                first = False
            else:
                append(', ')
            name = f.name
            limit -= len(name) + 2
            if limit <= 0:
                append('...')
                break
            append(name)
            append('=')
            if f.label == f.LABEL_REPEATED:
                limit -= 2
                append('[')
                first_sub = True
                for item in v:
                    if first_sub:
                        first_sub = False
                    else:
                        limit -= 2
                        append(', ')
                    if limit <= 0:
                        append('...')
                        break
                    rep = _format_value(item, limit, level - 1)
                    limit -= len(rep)
                    append(rep)
                append(']')
            else:
                rep = _format_value(v, limit, level - 1)
                limit -= len(rep)
                append(rep)
        append('>')
        return ''.join(buffer)

    return typ.__name__ + '<>'


import google.appengine.ext.appstats.formatting
google.appengine.ext.appstats.formatting._format_value = _format_value
