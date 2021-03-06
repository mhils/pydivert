# -*- coding: utf-8 -*-
# Copyright (C) 2016  Fabio Falcinelli
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
__author__ = 'fabio'


class MethodUnsupportedException(Exception):
    def __init__(self, message="The method is not supported in this driver version"):
        super(MethodUnsupportedException, self).__init__(self, message)


class AsyncCallFailedException(Exception):
    def __init__(self, message="AsyncCall could not be run"):
        super(AsyncCallFailedException, self).__init__(self, message)
