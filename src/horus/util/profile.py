#!/usr/bin/python
# -*- coding: utf-8 -*-
#-----------------------------------------------------------------------#
#                                                                       #
# This file is part of the Horus Project                                #
#                                                                       #
# Copyright (C) 2014 Mundo Reader S.L.                                  #
# Copyright (C) 2013 David Braam from Cura Project                      #
#                                                                       #
# Date: June 2014                                                       #
# Author: Jesús Arroyo Torrens <jesus.arroyo@bq.com>                    #
#                                                                       #
# This program is free software: you can redistribute it and/or modify  #
# it under the terms of the GNU General Public License as published by  #
# the Free Software Foundation, either version 3 of the License, or     #
# (at your option) any later version.                                   #
#                                                                       #
# This program is distributed in the hope that it will be useful,       #
# but WITHOUT ANY WARRANTY; without even the implied warranty of        #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          #
# GNU General Public License for more details.                          #
#                                                                       #
# You should have received a copy of the GNU General Public License     #
# along with this program. If not, see <http://www.gnu.org/licenses/>.  #
#                                                                       #
#-----------------------------------------------------------------------#

import os
import traceback
import math
import re
import zlib
import base64
import sys
import platform
import types

if sys.version_info[0] < 3:
	import ConfigParser
else:
	import configparser as ConfigParser

from horus.util import validators

#The settings dictionary contains a key/value reference to all possible settings. With the setting name as key.
settingsDictionary = {}
#The settings list is used to keep a full list of all the settings. This is needed to keep the settings in the proper order,
# as the dictionary will not contain insertion order.
settingsList = []

#Currently selected machine (by index) Cura support multiple machines in the same preferences and can switch between them.
# Each machine has it's own index and unique name.
_selectedMachineIndex = 0

class setting(object):
	"""
		A setting object contains a configuration setting. These are globally accessible trough the quick access functions
		and trough the settingsDictionary function.
		Settings can be:
		* profile settings (settings that effect the scan process and the scan result)
		* preferences (settings that effect how horus works and acts)
		* machine settings (settings that relate to the physical configuration of your machine)
		Settings have validators that check if the value is valid, but do not prevent invalid values!
		Settings have conditions that enable/disable this setting depending on other settings.
	"""
	def __init__(self, name, default, type, category, subcategory):
		self._name = name
		self._label = name
		self._tooltip = ''
		self._default = unicode(default)
		self._values = []
		self._type = type
		self._category = category
		self._subcategory = subcategory
		self._validators = []
		self._conditions = []

		if type is types.FloatType:
			validators.validFloat(self)
		elif type is types.IntType:
			validators.validInt(self)

		global settingsDictionary
		settingsDictionary[name] = self
		global settingsList
		settingsList.append(self)

	def setLabel(self, label, tooltip = ''):
		self._label = label
		self._tooltip = tooltip
		return self

	def setRange(self, minValue=None, maxValue=None):
		if len(self._validators) < 1:
			return
		self._validators[0].minValue = minValue
		self._validators[0].maxValue = maxValue
		return self

	def getLabel(self):
		return _(self._label)

	def getTooltip(self):
		return _(self._tooltip)

	def getCategory(self):
		return self._category

	def getSubCategory(self):
		return self._subcategory

	def isPreference(self):
		return self._category == 'preference'

	def isMachineSetting(self):
		return self._category == 'machine'

	def isProfile(self):
		return not self.isPreference() and not self.isMachineSetting()

	def getName(self):
		return self._name

	def getType(self):
		return self._type

	def getValue(self, index = None):
		if index is None:
			index = self.getValueIndex()
		if index >= len(self._values):
			return self._default
		return self._values[index]

	def getDefault(self):
		return self._default

	def setValue(self, value, index = None):
		if index is None:
			index = self.getValueIndex()
		while index >= len(self._values):
			self._values.append(self._default)
		self._values[index] = unicode(value)

	def getValueIndex(self):
		if self.isMachineSetting() or self.isProfile():
			global _selectedMachineIndex
			return _selectedMachineIndex
		return 0

	def validate(self):
		result = validators.SUCCESS
		msgs = []
		for validator in self._validators:
			res, err = validator.validate()
			if res == validators.ERROR:
				result = res
			elif res == validators.WARNING and result != validators.ERROR:
				result = res
			if res != validators.SUCCESS:
				msgs.append(err)
		return result, '\n'.join(msgs)

	def addCondition(self, conditionFunction):
		self._conditions.append(conditionFunction)

	def checkConditions(self):
		for condition in self._conditions:
			if not condition():
				return False
		return True

#########################################################
## Settings
#########################################################

#Define a fake _() function to fake the gettext tools in to generating strings for the profile settings.
def _(n):
	return n

#-- Settings
 
setting('step_degrees', 0.45, float, 'basic', _('Step Degrees')).setRange(0.1125)
setting('step_delay', 800, int, 'basic', _('Step Delay')).setRange(100, 10000)

setting('machine_name', '', str, 'machine', 'hidden')

setting('language', 'English', str, 'preference', 'hidden').setLabel(_('Language'), _('Change the language in which Horus runs. Switching language requires a restart of Horus'))


#Remove fake defined _() because later the localization will define a global _()
del _

#########################################################
## Profile and preferences functions
#########################################################

def getSubCategoriesFor(category):
	done = {}
	ret = []
	for s in settingsList:
		if s.getCategory() == category and not s.getSubCategory() in done and s.checkConditions():
			done[s.getSubCategory()] = True
			ret.append(s.getSubCategory())
	return ret

def getSettingsForCategory(category, subCategory = None):
	ret = []
	for s in settingsList:
		if s.getCategory() == category and (subCategory is None or s.getSubCategory() == subCategory) and s.checkConditions():
			ret.append(s)
	return ret

## Profile functions
def getBasePath():
	"""
	:return: The path in which the current configuration files are stored. This depends on the used OS.
	"""
	if platform.system() == "Windows":
		basePath = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
		#If we have a frozen python install, we need to step out of the library.zip
		if hasattr(sys, 'frozen'):
			basePath = os.path.normpath(os.path.join(basePath, ".."))
	else:
		basePath = os.path.expanduser('~/.horus/')
	if not os.path.isdir(basePath):
		try:
			os.makedirs(basePath)
		except:
			print "Failed to create directory: %s" % (basePath)
	return basePath

def getAlternativeBasePaths():
	"""
	Search for alternative installations of Horus and their preference files. Used to load configuration from older versions of Horus.
	"""
	paths = []
	basePath = os.path.normpath(os.path.join(getBasePath(), '..'))
	for subPath in os.listdir(basePath):
		path = os.path.join(basePath, subPath)
		if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'preferences.ini')) and path != getBasePath():
			paths.append(path)
		path = os.path.join(basePath, subPath, 'Horus')
		if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'preferences.ini')) and path != getBasePath():
			paths.append(path)
	return paths

def getDefaultProfilePath():
	"""
	:return: The default path where the currently used profile is stored and loaded on open and close of Horus.
	"""
	return os.path.join(getBasePath(), 'current_profile.ini')

def loadProfile(filename, allMachines = False):
	"""
		Read a profile file as active profile settings.
	:param filename:    The ini filename to save the profile in.
	:param allMachines: When False only the current active profile is saved. If True all profiles for all machines are saved.
	"""
	global settingsList
	profileParser = ConfigParser.ConfigParser()
	try:
		profileParser.read(filename)
	except ConfigParser.ParsingError:
		return
	if allMachines:
		n = 0
		while profileParser.has_section('profile_%d' % (n)):
			for set in settingsList:
				if set.isPreference():
					continue
				section = 'profile_%d' % (n)
				if profileParser.has_option(section, set.getName()):
					set.setValue(unicode(profileParser.get(section, set.getName()), 'utf-8', 'replace'), n)
			n += 1
	else:
		for set in settingsList:
			if set.isPreference():
				continue
			section = 'profile'
			if profileParser.has_option(section, set.getName()):
				set.setValue(unicode(profileParser.get(section, set.getName()), 'utf-8', 'replace'))
				
def saveProfile(filename, allMachines = False):
	"""
		Save the current profile to an ini file.
	:param filename:    The ini filename to save the profile in.
	:param allMachines: When False only the current active profile is saved. If True all profiles for all machines are saved.
	"""
	global settingsList
	profileParser = ConfigParser.ConfigParser()
	if allMachines:
		for set in settingsList:
			if set.isPreference() or set.isMachineSetting():
				continue
			for n in xrange(0, getMachineCount()):
				section = 'profile_%d' % (n)
				if not profileParser.has_section(section):
					profileParser.add_section(section)
				profileParser.set(section, set.getName(), set.getValue(n).encode('utf-8'))
	else:
		profileParser.add_section('profile')
		for set in settingsList:
			if set.isPreference() or set.isMachineSetting():
				continue
			profileParser.set('profile', set.getName(), set.getValue().encode('utf-8'))

	profileParser.write(open(filename, 'w'))

def resetProfile():
	""" Reset the profile for the current machine to default. """
	global settingsList
	for set in settingsList:
		if not set.isProfile():
			continue
		set.setValue(set.getDefault())

def setProfileFromString(options):
	"""
	Parse an encoded string which has all the profile settings stored inside of it.
	Used in combination with getProfileString to ease sharing of profiles.
	"""
	options = base64.b64decode(options)
	options = zlib.decompress(options)
	(profileOpts, alt) = options.split('\f', 1)
	global settingsDictionary
	for option in profileOpts.split('\b'):
		if len(option) > 0:
			(key, value) = option.split('=', 1)
			if key in settingsDictionary:
				if settingsDictionary[key].isProfile():
					settingsDictionary[key].setValue(value)
	for option in alt.split('\b'):
		if len(option) > 0:
			(key, value) = option.split('=', 1)
			if key in settingsDictionary:
				settingsDictionary[key].setValue(value)

def getProfileString():
	"""
	Get an encoded string which contains all profile settings.
	Used in combination with setProfileFromString to share settings in files, forums or other text based ways.
	"""
	p = []
	alt = []
	global settingsList
	for set in settingsList:
		if set.isProfile():
			p.append(set.getName() + "=" + set.getValue().encode('utf-8'))
	ret = '\b'.join(p) + '\f' + '\b'.join(alt)
	ret = base64.b64encode(zlib.compress(ret, 9))
	return ret

def insertNewlines(string, every=64): #This should be moved to a better place then profile.
	lines = []
	for i in xrange(0, len(string), every):
		lines.append(string[i:i+every])
	return '\n'.join(lines)

def getPreferencesString():
	"""
	:return: An encoded string which contains all the current preferences.
	"""
	p = []
	global settingsList
	for set in settingsList:
		if set.isPreference():
			p.append(set.getName() + "=" + set.getValue().encode('utf-8'))
	ret = '\b'.join(p)
	ret = base64.b64encode(zlib.compress(ret, 9))
	return ret


def getProfileSetting(name):
	"""
		Get the value of an profile setting.
	:param name: Name of the setting to retrieve.
	:return:     Value of the current setting.
	"""
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isProfile():
		return settingsDictionary[name].getValue()
	traceback.print_stack()
	sys.stderr.write('Error: "%s" not found in profile settings\n' % (name))
	return ''

def getProfileSettingFloat(name):
	try:
		setting = getProfileSetting(name).replace(',', '.')
		return float(eval(setting, {}, {}))
	except:
		return 0.0

def putProfileSetting(name, value):
	""" Store a certain value in a profile setting. """
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isProfile():
		settingsDictionary[name].setValue(value)

def isProfileSetting(name):
	""" Check if a certain key name is actually a profile value. """
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isProfile():
		return True
	return False

## Preferences functions
def getPreferencePath():
	"""
	:return: The full path of the preference ini file.
	"""
	return os.path.join(getBasePath(), 'preferences.ini')

def getPreferenceFloat(name):
	"""
	Get the float value of a preference, returns 0.0 if the preference is not a invalid float
	"""
	try:
		setting = getPreference(name).replace(',', '.')
		return float(eval(setting, {}, {}))
	except:
		return 0.0

def getPreferenceColour(name):
	"""
	Get a preference setting value as a color array. The color is stored as #RRGGBB hex string in the setting.
	"""
	colorString = getPreference(name)
	return [float(int(colorString[1:3], 16)) / 255, float(int(colorString[3:5], 16)) / 255, float(int(colorString[5:7], 16)) / 255, 1.0]

def loadPreferences(filename):
	"""
	Read a configuration file as global config
	"""
	global settingsList
	profileParser = ConfigParser.ConfigParser()
	try:
		profileParser.read(filename)
	except ConfigParser.ParsingError:
		return

	for set in settingsList:
		if set.isPreference():
			if profileParser.has_option('preference', set.getName()):
				set.setValue(unicode(profileParser.get('preference', set.getName()), 'utf-8', 'replace'))

	n = 0
	while profileParser.has_section('machine_%d' % (n)):
		for set in settingsList:
			if set.isMachineSetting():
				if profileParser.has_option('machine_%d' % (n), set.getName()):
					set.setValue(unicode(profileParser.get('machine_%d' % (n), set.getName()), 'utf-8', 'replace'), n)
		n += 1

def savePreferences(filename):
	global settingsList
	#Save the current profile to an ini file
	parser = ConfigParser.ConfigParser()
	parser.add_section('preference')

	for set in settingsList:
		if set.isPreference():
			parser.set('preference', set.getName(), set.getValue().encode('utf-8'))

	n = 0
	while getMachineSetting('machine_name', n) != '':
		parser.add_section('machine_%d' % (n))
		for set in settingsList:
			if set.isMachineSetting():
				parser.set('machine_%d' % (n), set.getName(), set.getValue(n).encode('utf-8'))
		n += 1
	parser.write(open(filename, 'w'))

def getPreference(name):
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isPreference():
		return settingsDictionary[name].getValue()
	traceback.print_stack()
	sys.stderr.write('Error: "%s" not found in preferences\n' % (name))
	return ''

def putPreference(name, value):
	#Check if we have a configuration file loaded, else load the default.
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isPreference():
		settingsDictionary[name].setValue(value)
		savePreferences(getPreferencePath())
		return
	traceback.print_stack()
	sys.stderr.write('Error: "%s" not found in preferences\n' % (name))

def isPreference(name):
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isPreference():
		return True
	return False

def getMachineSettingFloat(name, index = None):
	try:
		setting = getMachineSetting(name, index).replace(',', '.')
		return float(eval(setting, {}, {}))
	except:
		return 0.0

def loadMachineSettings(filename):
	global settingsList
	#Read a configuration file as global config
	profileParser = ConfigParser.ConfigParser()
	try:
		profileParser.read(filename)
	except ConfigParser.ParsingError:
		return

	for set in settingsList:
		if set.isMachineSetting():
			if profileParser.has_option('machine', set.getName()):
				set.setValue(unicode(profileParser.get('machine', set.getName()), 'utf-8', 'replace'))
	checkAndUpdateMachineName()

def getMachineSetting(name, index = None):
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isMachineSetting():
		return settingsDictionary[name].getValue(index)
	traceback.print_stack()
	sys.stderr.write('Error: "%s" not found in machine settings\n' % (name))
	return ''

def putMachineSetting(name, value):
	#Check if we have a configuration file loaded, else load the default.
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isMachineSetting():
		settingsDictionary[name].setValue(value)
	savePreferences(getPreferencePath())

def isMachineSetting(name):
	global settingsDictionary
	if name in settingsDictionary and settingsDictionary[name].isMachineSetting():
		return True
	return False