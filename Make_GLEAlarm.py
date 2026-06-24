#!/usr/bin/python3

"""
Copyright 2024-2025 Bartol Research Institute

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
See the NOTICE file distributed with this work for additional
information regarding copyright ownership.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
===========================================================================
# Make_GLEAlarm
# Script to analyze Neutron Monitor rates for Ground Level Enhacements (GLE)
# events and email alerts
#
# Auhors:
# Brian Lucas
# Pierre-Simon Mangeard
#
# Versions:
# 1.0.0 Production version maintained by Pierre-Simon Mangeard used as base for development
# 1.1.0 Disabling email sending for development
# 1.2.0 Added argument for archive and hard coded location of archive folder
# 1.3.0 Handle archive replay without lastemails.json and fill missing archive data
# 1.4.0 Add flag for daily data dumps. Station changes
# 1.5.0 Change replay imported zeros to NaN
# 1.6.0 Change to multi day replay
# 1.7.0 Combine station info into stations dataframe
# 1.8.0 Added indivdual baseline time, change baseline calc and hold baseline
# 1.9.0 Added basic mailman integration to send emails by injecting into queue
# 1.10.0 Changes to test archive replay on Windows Subsytem for Linux testbed
# 1.11.0 Add test mailman list for testing on wakko
# 1.12.0 Allow new live data to rerun previos minutes within a certain timeframe
# 1.13.0 Change source files and respect delay from real time
# 1.14.0 Output data for the web
# 1.15.0 Changes for production runs
# 1.16.0 Changes for email address and link
# 1.17.0 Change to baseline adjustment
# 1.18.0 Live Day files
# 1.19.0 Live updates with limited range into the past
# 1.20.0 Change how repeat alarms are handled during reruns back in time. Email format changes
# 1.21.0 Add html table to email format
# 1.22.0 Handle alert edge cases. Change email table back to markdown with padding for plain text render.
"""
import glob
from datetime import datetime, timedelta, timezone, date, time
import time
import numpy as np
import pandas as pd

import math
import csv
import json
import sys
import getopt
import gc

import ssl
import sqlite3

import os
# import os.path
from os import path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import ScalarFormatter
from matplotlib.cbook import get_sample_data
import matplotlib.gridspec as gridspec

from mailman.config import config
from mailman.core.initialize import initialize
from mailman.email.message import Message
from mailman.utilities.email import add_message_hash
from email.utils import formatdate, make_msgid
from email import message_from_bytes, message_from_string

from collections import namedtuple

# import smtplib
# from email.message import EmailMessage

#######################################
###Set Latex font for figures
#######################################
mpl.rcParams.update({
	'font.size':17,
	'text.usetex': False,
	'font.family': 'stixgeneral',
	'mathtext.fontset': 'stix',
})



__author__      = "Pierre-Simon Mangeard"
__credits__ = ["Pierre-Simon Mangeard"]
__email__ = "mangeard@udel.edu"

pd.options.mode.chained_assignment = None  # default='warn'

# def Add_Emailreceivers(filename,receivers):
#    print ("Error: Skipping receivers from {filename} for development") #DEBUG
# """
#    with open(filename, "r") as filestream:
#       for line in filestream:
#          line=line.rstrip('\n') #Clean end \n (sometimes needed)
#          currentline = line.split(",")
#          if len(currentline)>0: #Clean empty line
#             for i in range(len(currentline)):
#                if currentline[i]:#remove empty string
#                   receivers.append(currentline[i])

#  """
# def SendEmail(senders,receivers,message):
#    print ("Error: Skipping sending email to: {receivers} from: {senders} for development") #DEBUG
# """
#    try:
#       smtpObj = smtplib.SMTP('localhost')
#       smtpObj.sendmail(sender, receivers, message)
#       print ("Successfully sent email")
#    except:
#       print ("Error: unable to send email")
#        """

def main(argv):
   start_exetime = time.time()

   ########################
   ### DEFINE VARIABLES
   ########################
   Inpath = '.'      #input path
   #Inpath='d:/Documents/BartolData/ql'
   Outpath = '.'     #output path
   LocalOutpath = '.'     #output path
   #Outpath='d:/Documents/BartolData/ql'
   # Archivepath = '/home/lucasb/Archive/'     #archive path TODO add as arg
   Archivepath = '/home/lucasb/genNMDB/'     #archive path TODO add as arg
   isReplay = False #flag for replay functionality
   isProduction = False #flag for replay functionality
   replayStart = date.today() #flag for replay functionality
   dailyDump = False #flag to dump data to file daily
   Ndelay = 3        #Number of minutes of delay
   replayDays = 1
   initHours = 14
   #urlalarm="http://www.bartol.udel.edu/~takao/neutronm/glealarm/index.html"
   # urlalarm="https://neutronm.bartol.udel.edu/~mangeard/glealarm/GLE_Alarm.png"
   urlalarm="https://gle.bartol.udel.edu/"
   # urlalarm="./GLE_Alarm.png" #DEBUG

   Status=['Quiet','Watch','Warning','Alert']
   Statuscol=['gray','blue','orange','red']

   updateWindowMinutes = 60 #max number of past minutes to consider when getting realtime updates
   MailmanList = namedtuple('MailmanList',['condition','id','address'])
   # statusMMListsProd = [MailmanList(Status[1], 'glewatch.ex.localhost', 'glewatch@ex.localhost'),
   #                  MailmanList(Status[2], 'glewarning.ex.localhost', 'glewarning@ex.localhost'),
   #                  MailmanList(Status[3], 'glealert.ex.localhost', 'glealert@ex.localhost')]
   statusMMListsProd = [MailmanList(Status[1], 'glewatch.gle.bartol.udel.edu', 'glewatch@gle.bartol.udel.edu'),
                    MailmanList(Status[2], 'glewarning.gle.bartol.udel.edu', 'glewarning@gle.bartol.udel.edu'),
                    MailmanList(Status[3], 'glealert.gle.bartol.udel.edu', 'glealert@gle.bartol.udel.edu')]
   statusMMListsDev = [MailmanList(Status[1], 'gletest.gle.bartol.udel.edu', 'gletest@gle.bartol.udel.edu'),
                    MailmanList(Status[2], 'gletest.gle.bartol.udel.edu', 'gletest@gle.bartol.udel.edu'),
                    MailmanList(Status[3], 'gletest.gle.bartol.udel.edu', 'gletest@gle.bartol.udel.edu')]




   ########################
   ### ARGUMENTS
   ########################

   strinfo='Make_GLEAlarm.py: options:\n'
   strinfo=strinfo+'-n <Number of minutes of delay> \n'
   strinfo=strinfo+'-i <input path>\n'
   strinfo=strinfo+'-o <output path> (output path for sharing. Same as input path if not given)\n'
   strinfo=strinfo+'-g <local output path> (local output for Grafana. Same as input path if not given)\n'
   strinfo=strinfo+'-r <replay day> (in valid ISO 8601 format like YYYY-MM-DD)\n'
   strinfo=strinfo+'-d (flag to dump all data to GLE_Day file daily)\n'
   strinfo=strinfo+'-l <number of days to replay>\n'
   strinfo=strinfo+'-p (flag for production mailing lists)\n'

   try:
      opts, args = getopt.getopt(argv,"hn:i:o:g:r:dl:p")
   except getopt.GetoptError:
      print(strinfo)
      sys.exit(2)

   for opt, arg in opts:
      if opt == '-h':
         print(strinfo)
         sys.exit()
      elif opt in ("-n"):
         Ndelay = int(arg)      #Number of minutes of delay
      elif opt in ("-i"):
         Inpath = arg      #input path
         Outpath = arg     #output path
         LocalOutpath = arg     #local output path
      elif opt in ("-o"):
         Outpath = arg     #output path
      elif opt in ("-g"):
         LocalOutpath = arg     #local output path
      elif opt in ("-r"):
         isReplay = True #flag to turn on replay functionality
         replayStart = date.fromisoformat(arg) #set the start day
         print("{0:s} interpreted Replay Day {1:s}".format(arg, replayStart.strftime("%D")))
      elif opt in ("-d"):
         dailyDump = True #flag to dump data to file daily
      elif opt in ("-l"):
         replayDays = int(arg) #flag to dump data to file daily
      elif opt in ("-p"):
         isProduction = True #flag to dump data to file daily

   if len(opts) <  1:
      print('For information: Make_GLEAlarm.py -h')
      sys.exit(2)

   ########################
   #Data frame all minutes and hours of the last 15 days
   ########################

   # datetime object containing current date and time
   now = datetime.now(timezone.utc) - timedelta(minutes=Ndelay)
   now = now.replace(second = 0, microsecond = 0)

   if isProduction :
      statusMMLists = statusMMListsProd
      print("Production Mailing Lists!")
      print(statusMMLists)

   else:
      statusMMLists = statusMMListsDev

   if isReplay:
      now=datetime(year=replayStart.year, month=replayStart.month, day=replayStart.day, hour=initHours, minute=0, second=0, tzinfo=timezone.utc) #set to beginning of replay
   print("now =", now)
   end = now.strftime("%Y-%m-%d %H:%M")

   print('Mailman3 using config: /etc/mailman3/mailman.cfg')
   initialize('/etc/mailman3/mailman.cfg')

   #Read json files that contain 10 days
   # Ndays=10

   if not isReplay :
      initHours = 48

   startdt = now - timedelta(hours=initHours)
   start= startdt.strftime("%Y-%m-%d %H:%M")

   # print("date and time =", start) #DEBUG
   # print("date and time =", end) #DEBUG

   #Define full Ndays days data frame for count rates (minute rate)
   # rng=pd.date_range(start=start, end=end,freq='1min')
   rng=pd.date_range(start=startdt, end=now,freq='1min')
   Fulldf = pd.DataFrame({ 'Time': rng})
   Fulldf.index = Fulldf['Time']
   # print(Fulldf)  #DEBUG
   # print(pd.__version__)  #DEBUG

   ########################
   ### Stations to read
   ########################

   # nm=      ['in','fs','pe','na','ne','th','sp','sp','mc','jb']
   # nmdbtag= ['INVK','FSMT','PWNK','NAIN','NEWK','THUL','SOPO','SOPB','MCMU','JBGO']
   # Labels=  ['Inuvik','Fort Smith','Peawanuck','Nain','Newark','Thule','South Pole','$^{\dagger}$South Pole - bare','McMurdo','Jang Bogo']
   # InAlert= [1       ,1           ,1          ,1     ,0       ,1      ,1                       ,0                  ,1        ,0          ]
   # sFact= ['','',' *2','',' *2','',' /2','','','']
   # Fact=  [1.,1.,2.   ,1.,2.    ,1.,0.5 ,1.,1.,1.]

   #History from Makejson_ql.py
   #History= [0.597135,(0.598/0.94696),1.35333,0.59686,0.54518,0.57732*0.6,0.705,0.52308,0.52308]
   # History= [0.597135,0.598,1.35333,0.59686,0.54518,0.57732*0.6,0.52308,0.52308,0.705]
   # History=np.array(History)
   # History=History/0.6

   stations= pd.read_csv("NMStations.csv",index_col=0,dtype={'nmdbtag':pd.StringDtype(), 'InAlert':bool, 'nm':pd.StringDtype(), 'Labels':pd.StringDtype(), 'sFact':pd.StringDtype(), 'Fact':float, 'History':float})
   stations['History'] = stations['History'].apply(lambda x: x/0.6)
   # print(stations.info(verbose=True, show_counts=True))  #DEBUG
   if not isProduction : print(stations)  #DEBUG
   stations.loc[stations['Latitude'].fillna("N/A").str.startswith('90'), 'Longitude'] = "N/A"
   if not isProduction : print(stations)  #DEBUG
   #Number of stations
   # N= len(nm)-1
   N = len(stations)
   # print(N)  #DEBUG
   # sys.exit()  #DEBUG

   #if isReplay: N-=1 #DEBUG
   Notused='$^{\dagger}$Not used'

   raw_data=[]
   archive_data=[]
   fillerData = np.nan

   if isReplay:
      lastemails = {'Watch': datetime.strptime('1956-01-01 00:00:00', "%Y-%m-%d %H:%M:%S"), 'Warning': datetime.strptime('1956-01-01 00:00:00', "%Y-%m-%d %H:%M:%S"), 'Alert': datetime.strptime('1956-01-01 00:00:00', "%Y-%m-%d %H:%M:%S")} #1956-01-01 should be before any GLE to replay
      # fillerData = np.nan
      monthRowSkip = 1 #always skip header row of monthly minute file
      if replayStart.day >= 1:
         monthRowSkip = (24*(startdt.day-1))*60+1 #skip previous day and header row
      replayEnd = replayStart + timedelta(days=(replayDays-1))
      replayEnd = datetime(year=replayEnd.year, month=replayEnd.month, day=replayEnd.day, hour=23, minute=59, second=0, tzinfo=timezone.utc) #set to end of replay
      if not isProduction : print("end =", replayEnd) #DEBUG
      if not ((replayEnd.year == replayStart.year) and (replayEnd.month == replayStart.month)):
         if 12 == replayStart.month :
            replayRows = (24*60)*(date(year=replayStart.year+1,month=1,day=1)-replayStart).days
         else :
            replayRows = (24*60)*(date(year=replayStart.year,month=replayStart.month+1,day=1)-replayStart).days
         # print(replayRows) #DEBUG

      else:

         replayRows = (24*60)*replayDays #replay 24 hours and included
      # print(replayRows) #DEBUG
      # sys.exit() #DEBUG

      # prevRows = 0
      # if startdt.day >= 1:
      #    monthRowSkip = (10+(24*(startdt.day-1)))*60+1 # skip 10 hours of previous day and header row
      #    prevRows = initHours*60 # hours from prev
      # replayRows = prevRows + (24*60) #replay 24 hours and previous day rows included TODO handle last day
      # for i in range(N-1):
      # for i in range(N):
      for curIndex in stations.index:
         try:
            # print("reading archive file {0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt".format(Archivepath, nmdbtag[i], startdt.year, startdt.month)) #DEBUG
            # new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, nmdbtag[i], startdt.year, startdt.month), date_format= '%Y-%m-%d%H:%M:S', parse_dates=[[1,2]], names=['Time', '{0:s}'.format(nmdbtag[i]),  '{0:s}_P'.format(nmdbtag[i]), 'DELETEuncorr'], skiprows=(10+(24*(startdt.day-1)))*60+1, nrows=38*60, sep='\s+')
            # new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, nmdbtag[i], startdt.year, startdt.month), parse_dates=[0], date_format='%Y-%m-%d%', names=['Date', 'TimeOnly', '{0:s}'.format(nmdbtag[i]),  '{0:s}_P'.format(nmdbtag[i]), 'DELETEuncorr'], skiprows=(10+(24*(startdt.day-1)))*60+1, nrows=38*60, sep='\s+')
            if not isProduction : print('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, curIndex, startdt.year, startdt.month))  #DEBUG
            new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, curIndex, startdt.year, startdt.month), names=['Date', 'Time', '{0:s}'.format(curIndex),  '{0:s}_P'.format(curIndex), 'DELETEuncorr'], skiprows=monthRowSkip, nrows=replayRows, sep='\s+')
            # print(new_archive_data)  #DEBUG
            # print(new_archive_data['Time'].diff())  #DEBUG
            # sys.exit(-1)  #DEBUG
            if new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max() > 1.0:
               print('Archive data for {0:s} has greater than 1 min time delta between samples'.format(stations.at[curIndex,'Labels']))
               raise ValueError
            if len(new_archive_data) < replayRows:
               print('Archive data for {0:s} not long enough for replay'.format(stations.at[curIndex,'Labels']))
               raise ValueError

         except Exception as err:
            print('Exception {0} occured. {1:s} will be excluded from alert and filler data <{2}> will be used'.format(type(err), stations.at[curIndex,'Labels'], fillerData))
            # InAlert[i]=0
            stations.at[curIndex,'InAlert']=False #TODO modify something other than InAlert
            if stations.index.values[0]==curIndex:
               if not ((replayEnd.year == replayStart.year) and (replayEnd.month == replayStart.month)):
                  if 12 == replayStart.month :
                     archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end="{0:s}-31 23:59+0000".format(replayStart.strftime("%Y-%m")),freq='1min')})
                  else :
                     archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end=(datetime(year=replayStart.year, month=replayStart.month+1, day=1, hour=0, minute=0, second=0, tzinfo=timezone.utc)-timedelta(minutes=1)),freq='1min')})
               else :
                  archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end=replayEnd,freq='1min')})
               archive_data.index = archive_data['Time']
               archive_data=archive_data.drop(columns=['Time'])
               # print(archive_data)  #DEBUG
               # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG

            archive_data['{0:s}'.format(curIndex)]=fillerData
            archive_data['{0:s}_P'.format(curIndex)]=fillerData
         else:
            # new_archive_data.append(pd.read_csv("{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt".format(Archivepath, nmdbtag[i], startdt.year, startdt.month), names=["Date", "Time", "{0:s}".format(nmdbtag[i]),  "{0:s}_P".format(nmdbtag[i]), "DELETEuncorr"], skiprows=(10+(24*(startdt.day-1)))*60+1, nrows=38*60, sep='\s+'))
            # print(new_archive_data['Time'].to_numpy(dtype='datetime64[ns]'))  #DEBUG
            # print(new_archive_data['Time'].apply(lambda r: print(r[3:5])))  #DEBUG
            # print(new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max())  #DEBUG
            # print(new_archive_data['Time'].values)  #DEBUG
            new_archive_data['Time'] = new_archive_data.apply(lambda r: pd.Timestamp.combine(datetime.strptime(r['Date'], '%Y-%m-%d').date(), datetime.strptime(r['Time'], '%H:%M:%S').time()).tz_localize(timezone.utc), axis=1)

            # new_archive_data['Time'] = new_archive_data.apply(lambda r: pd.Timestamp.combine(datetime.strptime(r['Date'], '%Y-%m-%d').date(), datetime.strptime(r['Time'], '%H:%M:%S').time(), axis=1))
            # print(new_archive_data)  #DEBUG

            # new_archive_data=new_archive_data.drop(columns=['Date'])
            new_archive_data.index = new_archive_data['Time']
            # print(new_archive_data.info(verbose=True, show_counts=True))  #DEBUG

            # print(new_archive_data.loc[start])  #DEBUG
            new_archive_data=new_archive_data.drop(columns=['DELETEuncorr'])
            new_archive_data=new_archive_data.drop(columns=['Date'])
            new_archive_data=new_archive_data.drop(columns=['Time'])
            # print(new_archive_data.info(verbose=True, show_counts=True))  #DEBUG
            if stations.index.values[0]==curIndex:
               archive_data = new_archive_data
               #print(archive_data)  #DEBUG

            else:
               # new_archive_data=new_archive_data.drop(columns=['Time'])
               archive_data = archive_data.join(new_archive_data, how='left')
               # print(archive_data)  #DEBUG
            # print(archive_data.loc[0])  #DEBUG
            if not isProduction : print(archive_data.info(verbose=True, show_counts=True))  #DEBUG




            """raw_data[-1]['Time'] =pd.to_datetime(raw_data[-1]['Time'],infer_datetime_format=True)
            raw_data[-1]['Time'] = raw_data[-1]['Time'].dt.tz_localize(None)
            raw_data[-1].index = raw_data[-1]['Time']
            raw_data[-1]=raw_data[-1].drop(columns=['Time'])
            raw_data[-1].to_csv('{0:s}/GLE_Alarm_{1:s}.txt'.format(Outpath,nm[i]), sep=',',date_format='%y/%m/%d %H:%M:%S') """

         # sys.exit(-1)  #DEBUG
      # print(archive_data.isna().sum())  #DEBUG
      archive_data = archive_data.mask(0.0==archive_data) #Make 0.0 values NaN
      # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG

      # print(archive_data.isna().sum())  #DEBUG
      # sys.exit()  #DEBUG

      # print(archive_data)  #DEBUG
      prevRows = 60*initHours
      raw_data = archive_data[:(prevRows+1)]
      archive_data = archive_data[(prevRows+1):]

      # print(raw_data)  #DEBUG
      # print(archive_data)  #DEBUG
      # print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG

      # df = Fulldf.join(raw_data, how='left')
      # print(raw_data.info(verbose=True, show_counts=True))  #DEBUG
      if not isProduction : print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
      # sys.exit()  #DEBUG

      stations.loc[False==stations['InAlert'],'Labels'] = '$^{\dagger}$' + stations[False==stations['InAlert']]['Labels']
      # print(stations)  #DEBUG




   else:
      # with open(Inpath+'/'+'lastemails.json') as lastemailsjson:
      with open('./lastemails.json') as lastemailsjson:
            lastemails = json.load(lastemailsjson)
      if not isProduction : print(lastemails)  #DEBUG

      dfFuture = None

      monthRowSkip = 1
      replayEnd=now
      replayStart = replayEnd - timedelta(hours=initHours)
      replayRows = initHours * 60
      # for i in range(N-1):
      for curIndex in stations.index:
         try:
            # raw_data.append(pd.read_json(Inpath+'/'+nm[i]+'_ql_l'+str(Ndays)+'d_1min.json'))
            # raw_data[-1]['Time'] =pd.to_datetime(raw_data[-1]['Time'],infer_datetime_format=True)
            # raw_data[-1]['Time'] = raw_data[-1]['Time'].dt.tz_localize(None)
            # raw_data[-1].index = raw_data[-1]['Time']
            # raw_data[-1]=raw_data[-1].drop(columns=['Time'])
            # raw_data[-1].to_csv('{0:s}/GLE_Alarm_{1:s}.txt'.format(Outpath,nm[i]), sep=',',date_format='%y/%m/%d %H:%M:%S')
            if not isProduction : print(Inpath+curIndex+'_2days.txt') #DEBUG
            new_archive_data = pd.read_csv(Inpath+curIndex+'_2days.txt', names=['Date', 'Time', '{0:s}'.format(curIndex),  '{0:s}_P'.format(curIndex), 'DELETEuncorr'], skiprows=monthRowSkip, sep='\s+')
            # print(new_archive_data) #DEBUG
            # print(new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max()) #DEBUG

            if new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max() > 1.0:
               if not isProduction : print('Warning: Archive data for {0:s} has greater than 1 min time delta between samples'.format(stations.at[curIndex,'Labels']))
               # raise ValueError
            if len(new_archive_data) < 100:
            # if len(new_archive_data) < replayRows:
               print('Archive data for {0:s} not long enough for replay'.format(stations.at[curIndex,'Labels']))
               raise ValueError

            # new_archive_data['Time'] = new_archive_data['Time'].dt.tz_localize(None)


         except Exception as err:
            print('Exception {0} occured. {1:s} will be excluded from alert and filler data <{2}> will be used'.format(type(err), stations.at[curIndex,'Labels'], fillerData))
            stations.at[curIndex,'InAlert']=False #TODO modify something other than InAlert
            if stations.index.values[0]==curIndex:
               if not ((replayEnd.year == replayStart.year) and (replayEnd.month == replayStart.month)):
                  if 12 == replayStart.month :
                     archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end="{0:s}-31 23:59+0000".format(replayStart.strftime("%Y-%m")),freq='1min')})
                  else :
                     archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end=(datetime(year=replayStart.year, month=replayStart.month+1, day=1, hour=0, minute=0, second=0, tzinfo=timezone.utc)-timedelta(minutes=1)),freq='1min')})
               else :
                  archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end=replayEnd,freq='1min')})
               archive_data.index = archive_data['Time']
               archive_data=archive_data.drop(columns=['Time'])


            archive_data['{0:s}'.format(curIndex)]=fillerData
            archive_data['{0:s}_P'.format(curIndex)]=fillerData
         else:
            new_archive_data['Time'] = new_archive_data.apply(lambda r: pd.Timestamp.combine(datetime.strptime(r['Date'], '%Y-%m-%d').date(), datetime.strptime(r['Time'], '%H:%M:%S').time()).tz_localize(timezone.utc), axis=1)

            new_archive_data.index = new_archive_data['Time']

            stations.at[curIndex,'ModTime']=os.path.getmtime(Inpath+curIndex+'_2days.txt')
            if not isProduction : print(stations.loc[curIndex])  #DEBUG



            # # Filter for current month to produce NMDB formatted file
            # new_archive_data_nmdb = new_archive_data[new_archive_data.index.month == now.month]

            # # Resample to 1-minute frequency and fill missing values with NaN
            # # new_archive_data_nmdb = new_archive_data_nmdb.resample('1min').asfreq()
            # full_month_index = pd.date_range(start=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end=now, freq='min')
            # new_archive_data_nmdb = new_archive_data_nmdb.reindex(full_month_index)

            # # Restore original column order (all columns)
            # new_archive_data_nmdb = new_archive_data_nmdb.rename(columns={'Date': 'YYYY-MM-DD', 'Time': 'hh:mm:ss', '{0:s}'.format(curIndex): 'corr', '{0:s}_P'.format(curIndex): 'press', 'DELETEuncorr': 'uncorr'})
            # new_archive_data_nmdb['YYYY-MM-DD'] = new_archive_data_nmdb.index.strftime('%Y-%m-%d')
            # new_archive_data_nmdb['hh:mm:ss'] = new_archive_data_nmdb.index.strftime('%H:%M:%S')
            # new_archive_data_nmdb = new_archive_data_nmdb.fillna(0.0)


            # # Save with original header format
            # output_file_nmdb = '{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format('/home/lucasb/genNMDB/', curIndex, now.year, now.month)
            # new_archive_data_nmdb.to_csv(output_file_nmdb, sep=' ', index=False, float_format='%.2f')

            # print(f"Saved: {output_file_nmdb}")

            new_archive_data=new_archive_data.drop(columns=['DELETEuncorr'])
            new_archive_data=new_archive_data.drop(columns=['Date'])
            new_archive_data=new_archive_data.drop(columns=['Time'])


            new_archive_data=new_archive_data[new_archive_data.index >= Fulldf.index[0]]
            if stations.index.values[0]==curIndex:
               # archive_data = new_archive_data
               # print(Fulldf)  #DEBUG
               # print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG
               archive_data = Fulldf.join(new_archive_data, how='left')

            else:
               archive_data = archive_data.join(new_archive_data, how='left')

            # print(archive_data)  #DEBUG
            if not isProduction : print(archive_data.info(verbose=True, show_counts=True))  #DEBUG

      # raw_data = archive_data.drop(columns=['Time'])
      raw_data = archive_data
      # print(raw_data)  #DEBUG
      if not isProduction : print(raw_data.info(verbose=True, show_counts=True))  #DEBUG
      # sys.exit() #DEBUG


   # print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG
   # print(raw_data.info(verbose=True, show_counts=True))  #DEBUG
   Fulldf=Fulldf.drop(columns=['Time'])
   if not isProduction : print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG
   df = Fulldf.join(raw_data, how='left')
   # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
   #df.to_csv('{0:s}/GLE_Alarm.txt'.format(Outpath), sep=',',date_format='%y/%m/%d %H:%M:%S')
   # print('InAlert')  #DEBUG
   # print(stations[True==stations['InAlert']])  #DEBUG
   alertFlagsList = stations[True==stations['InAlert']].index.values.map(lambda x: x + 'F')
   print("Stations in alert:", alertFlagsList)
   modFileStations = stations[0<stations['ModTime']].index.values
   print("Stations to check for updates:", modFileStations)
   # sys.exit() #DEBUG

   """print (df)
   print(df.info(verbose=True, show_counts=True))  #DEBUG
   sys.exit() #DEBUG
   """
   ########################
   ### Trailing moving average
   ########################
   #As defined by Kuwabara et al, (2006)
   #Kuwabara, T., J. W. Bieber, J. Clem, P. Evenson, and R. Pyle (2006), Development of a ground level enhancement
   #alarm system based upon neutron monitors, Space Weather, 4, S10001, doi:10.1029/2006SW000223.

   T=3
   T0=10
   Tb=75
   Level=4 #4%alert
   if not isProduction : Level=1 #DEBUG lot of watches


   # for i in range(N):
   for curIndex in stations.index:
      # df[curIndex+'T']=df[curIndex].rolling(str(T)+'min',min_periods=T).mean()
      # df[curIndex+'T']=df[curIndex+'T'] *60/stations.at[curIndex,'History']    #Get real count/minute (without historical normalization)
      # df[curIndex+'T']=df[curIndex].rolling(str(T)+'min',min_periods=T).mean()*(60/stations.at[curIndex,'History'])    #Get real count/minute (without historical normalization)
      # TODO talk about the min samples needed
      df[curIndex+'T']=df[curIndex].rolling(str(T)+'min',min_periods=T).mean()*(60/stations.at[curIndex,'History'])    #Get real count/minute (without historical normalization)
      # df[curIndex+'T']=df[curIndex].rolling(str(T)+'min',min_periods=1).mean()*(60/stations.at[curIndex,'History'])    #Get real count/minute (without historical normalization)
      # df[curIndex+'T0']=df[curIndex].rolling(str(T0)+'min',min_periods=T0-1).mean()
      # df[curIndex+'Tb0']=df[curIndex].rolling(str(Tb+T0)+'min',min_periods=Tb).mean()
      # df[curIndex+'Tb']=((Tb+T0)*df[curIndex+'Tb0']-T0*df[curIndex+'T0'])/Tb  * 60/stations.at[curIndex,'History']
      # df[curIndex+'T0']=df[curIndex].rolling(str(T0)+'min',min_periods=T0).mean()
      # df[curIndex+'Tb']=df[curIndex].rolling(str(Tb)+'min',min_periods=Tb).mean()*(60/stations.at[curIndex,'History'])
      # TODO talk about the min samples needed
      df[curIndex+'Tb']=df[curIndex].rolling(str(Tb)+'min',min_periods=(Tb-T0)).mean()*(60/stations.at[curIndex,'History'])
      # df[curIndex+'Tb']=df[curIndex].rolling(str(Tb)+'min',min_periods=1).mean()*(60/stations.at[curIndex,'History'])
      # print(df[curIndex+'T']) #DEBUG
      # print(df[curIndex+'Tb']) #DEBUG
      # print(df[curIndex+'Tb'].shift(periods=T0, fill_value=np.nan)) #DEBUG
      df[curIndex+'Ith']=df[curIndex+'T']/(df[curIndex+'Tb'].shift(periods=T0,fill_value=np.nan))
      # print(df[curIndex+'Ith']) #DEBUG
      # sys.exit()  #DEBUG
      df[curIndex+'F'] = np.where(df[curIndex+'Ith']< 1.+Level/100., 0, 1)
      df[curIndex+'F'] = pd.array(np.where(np.isnan(df[curIndex+'Ith']), 0,  df[curIndex+'F']), dtype=pd.Int8Dtype())
   # print(df.index[-T0])  #DEBUG
   # stations['BaselineTime']=df.index[-T0]
   stations['BaselineTime']=df.last_valid_index() - timedelta(minutes=T0)  #TODO handle a differetn starting baseline
   if not isProduction : print(stations.at[stations.first_valid_index(),'BaselineTime'])  #DEBUG
   if not isProduction : print(df.last_valid_index())  #DEBUG
   if not isProduction : print(stations)  #DEBUG
   if not isProduction : print(stations.info(verbose=True, show_counts=True))  #DEBUG


   # print(df.dtypes)  #DEBUG

   # for i in range(N):
   #    #df=df.drop(columns=[nmdbtag[i]])
   #    df=df.drop(columns=[nmdbtag[i]+'T0'])
   #    df=df.drop(columns=[nmdbtag[i]+'Tb0'])
   #    df=df.drop(columns=[nmdbtag[i]+'Tb'])

   ########################
   #CALULATE THE NUMBER OF STATIONS ABOVE THE LEVEL
   ########################

   # Nabove=np.zeros(len(df))
   # for i in range(N):
   #    if InAlert[i]==1:
   #       Nabove+=df[nmdbtag[i]+'F']
   # df['Nabove']=Nabove
   # df['Nabove']=df[stations[True==stations['InAlert']].index.values.map(lambda x: x + 'F')].sum(axis=1)
   df['Nabove']=df[alertFlagsList].sum(axis=1)

   # print(df.info(verbose=True, show_counts=True))  #DEBUG
   # print(df['Nabove'].sum(axis=0))  #DEBUG
   # print(df[df['Nabove']>0][stations[True==stations['InAlert']].index.values.map(lambda x: x + 'F')])  #DEBUG
   ########################
   #Define Status
   ########################
   #0: Quiet
   #1: Watch
   #2: Warning
   #>=3: Alert

   # Status=['Quiet','Watch','Warning','Alert']
   # Statuscol=['gray','blue','orange','red']
   # df['Status'] = np.where(df['Nabove']==0, 0.,df['Nabove'])
   # df['Status'] = np.where(df['Nabove']>=3, 3.,df['Status'])
   df['Status']=pd.array(df['Nabove'].apply(lambda x: 3 if x > 3 else x), dtype=pd.Int8Dtype())
   LastStatus = df.iloc[-2]['Status']




   # print(df.dtypes)  #DEBUG


   # print(LastStatus)  #DEBUG
   # print(df['Nabove'].max())  #DEBUG
   if not isProduction : print(df['Status'].max())  #DEBUG
   # print(df.last_valid_index()) #DEBUG


   # print(df.at[df.last_valid_index(),stations.index.values[0]+'Ith'])  #DEBUG
   # print(np.isnan(df.at[df.last_valid_index(),stations.index.values[0]+'Ith']))  #DEBUG

   # print(df.at[df.last_valid_index(),stations.index.values[0]+'Ith']< (1.+Level/100.))  #DEBUG


   if not isProduction : print(df)  #DEBUG
   if not isProduction : print(df.info(verbose=True, show_counts=True))  #DEBUG
   # sys.exit()  #DEBUG

   while(True): #will break when out of archive_data but will always run once


      earliestBaselineTime = pd.to_datetime(stations['BaselineTime'].values.min(), utc=True)#.astype(datetime)
      if not isProduction :

         print('Times ', df.last_valid_index(),  earliestBaselineTime)  #DEBUG
         print('Baseline time delta = ', ((df.last_valid_index() - earliestBaselineTime).total_seconds() / timedelta(minutes=1).total_seconds()))  #DEBUG
      for curIndex in stations.index:
         #TODO check calc
         # df.at[df.last_valid_index(),curIndex+'T']=df[curIndex].tail(3).mean()
         # df.at[df.last_valid_index(),curIndex+'T']=df.at[df.last_valid_index(),curIndex+'T'] *60/stations.at[curIndex,'History']    #Get real count/minute (without historical normalization)
         dfT = df[curIndex].tail(T)
         if T == dfT.count() :
            df.at[df.last_valid_index(),curIndex+'T']=dfT.mean()*(60/stations.at[curIndex,'History'])   #Get real count/minute (without historical normalization)
         else :
           df.at[df.last_valid_index(),curIndex+'T'] = np.nan
         # df.at[df.last_valid_index(),curIndex+'T']=df[curIndex].tail(T).mean()*(60/stations.at[curIndex,'History'])   #Get real count/minute (without historical normalization)
         # df.at[df.last_valid_index(),curIndex+'T0']=df[curIndex].tail(T0).mean()
         # df.at[df.last_valid_index(),curIndex+'Tb0']=df[curIndex].tail(Tb+T0).head(Tb).mean()
         # df.at[df.last_valid_index(),curIndex+'Tb0']=df[curIndex].tail(Tb+T0).mean()
         # df.at[df.last_valid_index(),curIndex+'Tb']=((Tb+T0)*df.at[df.last_valid_index(),curIndex+'Tb0']-T0*df.at[df.last_valid_index(),curIndex+'T0'])/Tb  * 60/stations.at[curIndex,'History']
         dfTb = df[curIndex].tail(Tb)
         if dfTb.count() >= (Tb -T0) :
            df.at[df.last_valid_index(),curIndex+'Tb']=dfTb.mean()*(60/stations.at[curIndex,'History'])
         else :
            df.at[df.last_valid_index(),curIndex+'Tb']=np.nan
         # df.at[df.last_valid_index(),curIndex+'Tb']=df[curIndex].tail(Tb).mean()*(60/stations.at[curIndex,'History'])
         df.at[df.last_valid_index(),curIndex+'Ith']=df.at[df.last_valid_index(),curIndex+'T']/df.at[stations.at[curIndex,'BaselineTime'],curIndex+'Tb'] #TODO possible key error

         # print(df.iloc[-1])  #DEBUG
         # print(df.at[df.last_valid_index(),curIndex+'Ith'])  #DEBUG
         # print(df.at[df.last_valid_index(),curIndex+'Ith']< (1.+Level/100.))  #DEBUG

         # if np.isnan(df.at[df.last_valid_index(),curIndex+'Ith']):
         if math.isnan(df.at[df.last_valid_index(),curIndex+'Ith']):
            df.at[df.last_valid_index(),curIndex+'F'] = int(0)
         else :
            if (df.at[df.last_valid_index(),curIndex+'Ith']< (1.+Level/100.)):
               df.at[df.last_valid_index(),curIndex+'F'] = int(0)
            else:
               df.at[df.last_valid_index(),curIndex+'F'] = int(1)
         # df.at[df.last_valid_index(),curIndex+'F'] = np.where(), 0.,  df[curIndex+'F'])
         # print(df[curIndex].tail(Tb+T0).head(Tb).index.values[0])
      # df.at[df.last_valid_index(),'Nabove']=df.loc[df.last_valid_index()][stations[True==stations['InAlert']].index.values.map(lambda x: x + 'F')].sum()
      df.at[df.last_valid_index(),'Nabove']=df.loc[df.last_valid_index()][alertFlagsList].sum()
      df.at[df.last_valid_index(),'Status']=3 if df.at[df.last_valid_index(),'Nabove'] > 3 else df.at[df.last_valid_index(),'Nabove']

      # print(df.dtypes)  #DEBUG

      # print(df.iloc[-1:]) #DEBUG
      # sys.exit()  #DEBUG

      ########################
      ### SEND EMAIL IF NEEDED
      ########################

      if (isReplay):
         #TODO emails
         if (df.at[df.last_valid_index(),'Status']>LastStatus):
            # print(df.last_valid_index())  #DEBUG
            # print(df.loc[df.last_valid_index()])  #DEBUG
            # print(df.dtypes)  #DEBUG
            if not isProduction : print(LastStatus)  #DEBUG

            msg = Message()

            # body= "{0:s} (UT): {1:s} alarm\n".format(df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),Status[df.at[df.last_valid_index(),'Status']])
            body= "{0:s} (UT): {1:s} alarm\n".format(df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),Status[df.at[df.last_valid_index(),'Status']])
            body=body+"Rate increase(s):\n"
            # for i in range(N):
            for curIndex in stations.index:
               if stations.at[curIndex,'InAlert'] and df.iloc[-1][curIndex+'F'] ==1:
                  # body=body+"{0:s} ({1:s}): {2:s} (UT), {3:4.2f}%\n".format(stations.at[curIndex,'Labels'],curIndex,df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),100.*(df.iloc[-1][curIndex+'Ith']-1.))
                  body=body+"{0:s} ({1:s}): {2:s} (UT), {3:4.2f}%\n".format(stations.at[curIndex,'Labels'],curIndex,df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),100.*(df.at[df.last_valid_index(),curIndex+'Ith']-1.))
            # body=body+"{0:s}\n".format(urlalarm)
            body=body+"Keep up with the latest developments at {0:s}\n".format(urlalarm)

            msg['To'] = statusMMLists[df.at[df.last_valid_index(),'Status']-1].address
            # msg['From'] = 'glealarm@yahoo.com'
            msg['From'] = 'gle-alarm@udel.edu'
            # msg['From'] = statusMMLists[LastStatus].address + ' list Via <glealarm@yahoo.com>'
            # msg['From'] = 'gletest@ex.localhost'
            # msg['Subject'] = """gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[df.at[df.last_valid_index(),'Status']],df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"))
            msg['Subject'] = """gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[df.at[df.last_valid_index(),'Status']],df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"))
            msg['Message-ID'] = make_msgid()
            msg['Date'] = formatdate(localtime=True)
            # print(msg)
            msg.set_payload(body)
            # print(msg)
            msg.original_size = len(msg.as_string())
            add_message_hash(msg)
            msgdata = dict(
               listid=statusMMLists[df.at[df.last_valid_index(),'Status']-1].id,
               original_size=msg.original_size)
            if not isProduction : print(msg)  #DEBUG
            if not isProduction : print(msgdata)  #DEBUG
            config.switchboards['in'].enqueue(msg, **msgdata)


            # df.iloc[-360:].to_csv('{0:s}/{1:s}/GLE_{1:s}_{2:s}.txt'.format(
            #             LocalOutpath,Status[df.at[df.last_valid_index(),'Status']],now.strftime("%Y%m%d_%H%M%S")),
            #             sep=',',date_format='%y/%m/%d %H:%M:%S')
            df.iloc[-360:].to_csv('{0:s}/Alarms/{1:s}/GLE_{1:s}_{2:s}.csv'.format(
                        Outpath,Status[df.at[df.last_valid_index(),'Status']],now.strftime("%Y%m%d_%H%M%S")),
                        sep=',',index=True,date_format='%Y-%m-%dT%H:%M:%SZ')
         LastStatus=df.at[df.last_valid_index(),'Status']
      else:
         #Load time when the last alarm emails were sent

         if (df.at[df.last_valid_index(),'Status']>LastStatus):
            if (df.last_valid_index() > pd.to_datetime(lastemails[Status[df.at[df.last_valid_index(),'Status']]], utc=True)) :
               # print(df.last_valid_index())  #DEBUG
               # print(df.loc[df.last_valid_index()])  #DEBUG
               # print(df.dtypes)  #DEBUG
               if not isProduction : print("Status Change ", LastStatus, " to ", df.at[df.last_valid_index(),'Status'])  #DEBUG

               lastemails[Status[df.at[df.last_valid_index(),'Status']]] = df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S")

               
               df_active = (
                  df[stations.index.values.map(lambda x: x + 'F')]
                  .loc[:, lambda x: x.iloc[-1] == 1]
               )

               if not isProduction : print(df.info(verbose=True, show_counts=True))  #DEBUG
               colActive = df_active.columns.tolist()
               if (len(colActive) > 0) :
                  colActive = [item[:-1] for item in colActive]
               else :
                  colActive = None

               df_active = df_active[df_active.index >= (earliestBaselineTime - pd.Timedelta(minutes=(Tb+T0)))] #Most threshold inc should start in this window

               if (df_active.sum(axis=1).max() >= len(df_active)) :
                  df_active = df[stations.index.values.map(lambda x: x + 'F')].loc[:, lambda x: x.iloc[-1] == 1]

               transitions = (df_active.shift() == 0) & (df_active == 1)


               if not isProduction : print(transitions[transitions.any(axis=1)])  #DEBUG
               msg = Message()

               # body= "{0:s} (UT): {1:s} alarm\n".format(df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),Status[df.at[df.last_valid_index(),'Status']])
               body= "{0:s} (UT): {1:s} alarm\n".format(df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),Status[df.at[df.last_valid_index(),'Status']])
               # body=body+"Rate increase(s):\n"
               body=body+"\n**Station Summary:** \n"
               body=body+"| Station Name    (CODE) | Latitude (°)   | Longitude (°)  | Threshold Time (UTC)   | Increase (%)   |\n"
               # body=body+"|:-----------------------|:---------------|:-----------------|:------------------------|:---------------|\n"
               body=body+"|:-----------------------|:---------------|:---------------|:-----------------------|---------------:|\n"
               # body=body+"<html><body><p><strong>Station Summary:</strong></p><table border=\"1\" cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse: collapse;\"><thead><tr><th>Station Name</th><th>Latitude (°)</th><th>Longitude (°)</th><th>Threshold Time (UTC)</th><th>Increase (%)</th></tr></thead><tbody>\n"
    

               # for i in range(N):
               # for curIndex in stations.index:
               for curIndex in colActive:
                  if stations.at[curIndex,'InAlert'] and df.iloc[-1][curIndex+'F'] ==1:
                     # body=body+"{0:s} ({1:s}): {2:s} (UT), {3:4.2f}%\n".format(stations.at[curIndex,'Labels'],curIndex,df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),100.*(df.iloc[-1][curIndex+'Ith']-1.))
                     # body=body+"{0:s} ({1:s}): {2:s} (UT), {3:4.2f}%\n".format(stations.at[curIndex,'Labels'],curIndex,df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),100.*(df.at[df.last_valid_index(),curIndex+'Ith']-1.))
                     # body=body+"{0:s} ({1:s})\t| \t\t\t| \t\t\t| {2:s} (UT)\t| {3:4.2f}%\n".format(stations.at[curIndex,'Labels'],curIndex,df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),100.*(df.at[df.last_valid_index(),curIndex+'Ith']-1.))
                     # body=body+"<tr> <td>{0:s} ({1:s})<td> <td> <td>{2:s} (UT) <td>{3:4.2f}%</tr>\n".format(stations.at[curIndex,'Labels'],curIndex,df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),100.*(df.at[df.last_valid_index(),curIndex+'Ith']-1.))
                     # body=body+"|{0:s} ({1:s})| {2:s} | {3:s} | {4:s} (UT) | {3:4.2f}% |\n".format(stations.at[curIndex,'Labels'],curIndex,,' ',' ',df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),100.*(df.at[df.last_valid_index(),curIndex+'Ith']-1.))
                     
                     # body = body + "| {:<15} ({:<4}) | {:<14} | {:<15} | {:<22} | {:<12} |\n".format(
                     body = body + "| {:<15} ({:<4}) | {:<14} | {:<14} | {:<22} | {:>8} |\n".format(
                        stations.at[curIndex, 'Labels'],
                        curIndex,
                        stations.at[curIndex, 'Latitude'],  
                        stations.at[curIndex, 'Longitude'],  
                        # df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"),
                        transitions.index[transitions[curIndex+'F']][-1].strftime("%Y-%m-%d %H:%M:%S"),
                        "{:4.2f}%".format(100. * (df.at[df.last_valid_index(), curIndex + 'Ith'] - 1.))
                     )

               # body=body+"{0:s}\n".format(urlalarm)
               body=body+"\nKeep up with the latest developments at {0:s}\n".format(urlalarm)
               # body=body+"</tbody></table></body></html>\nKeep up with the latest developments at {0:s}\n".format(urlalarm)


               msg['To'] = statusMMLists[df.at[df.last_valid_index(),'Status']-1].address #TODO consider sending to lower level lists
               # msg['From'] = 'glealarm@yahoo.com'
               msg['From'] = 'gle-alarm@udel.edu'
               # msg['From'] = statusMMLists[LastStatus].address + ' list Via <glealarm@yahoo.com>'
               # msg['From'] = 'gletest@ex.localhost'
               # msg['Subject'] = """gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[df.at[df.last_valid_index(),'Status']],df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"))
               msg['Subject'] = """gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[df.at[df.last_valid_index(),'Status']],df.last_valid_index().strftime("%Y-%m-%d %H:%M:%S"))
               msg['Message-ID'] = make_msgid()
               msg['Date'] = formatdate(localtime=True)
               # print(msg)
               msg.set_payload(body)
               # print(msg)
               msg.original_size = len(msg.as_string())
               add_message_hash(msg)
               msgdata = dict(
                  listid=statusMMLists[df.at[df.last_valid_index(),'Status']-1].id,
                  original_size=msg.original_size)
               if not isProduction : print(msg)  #DEBUG
               if not isProduction : print(msgdata)  #DEBUG
               config.switchboards['in'].enqueue(msg, **msgdata)


               df.iloc[-360:].to_csv('{0:s}/Alarms/{1:s}/GLE_{1:s}_{2:s}.csv'.format(
                           Outpath,Status[df.at[df.last_valid_index(),'Status']],now.strftime("%Y%m%d_%H%M%S")),
                           sep=',',index=True,date_format='%Y-%m-%dT%H:%M:%SZ')
            elif not isProduction : print(df.last_valid_index() , ' not after ',  pd.to_datetime(lastemails[Status[df.at[df.last_valid_index(),'Status']]], utc=True))  #DEBUG
            LastStatus=df.at[df.last_valid_index(),'Status']

      #    with open(Inpath+'/'+'lastemails.json') as lastemailsjson:
      #       lastemails = json.load(lastemailsjson)
      #    #Format time to timestamp
      #    for i in range(3):
      #          lastemails[Status[i+1]] =pd.to_datetime(lastemails[Status[i+1]],infer_datetime_format=True)
      #    # print(lastemails)  #DEBUG
      #    #Sender
      #    # sender = 'mangeard@spacewx.bartol.udel.edu'
      #    sender = 'sender@example.com' #DEBUG
      #    #Header
      #    #header= """From: mangeard@udel.edu\nTo: mangeard@udel.edu\n"""
      #    #header= """From: Pierre-Simon Mangeard  <mangeard@udel.edu>\nTo: Pierre-Simon Mangeard <mangeard@udel.edu>\n"""
      #    # header= """From: GLE Alarm  <glealarm-noreply@udel.edu>\nTo: Pierre-Simon Mangeard <mangeard@udel.edu>\n"""
      #    header= """From: GLE Alarm  <noreply@example.com>\nTo: Pierre-Simon Mangeard <sender@example.com>\n"""  #DEBUG

      #    # Bcc= """Bcc: psmangeard@gmail.com \n"""
      #    Bcc= """Bcc: sender@example.com \n"""
      #    #Text files containing the email lists
      #    # fmail=[Inpath+"/mail_to_watch.txt",Inpath+"/mail_to_wning.txt",Inpath+"/mail_to_alert.txt"]
      #    fmail=[Inpath+"/mail_to_watch_fake.txt",Inpath+"/mail_to_wning_fake.txt",Inpath+"/mail_to_alert_fake.txt"] #DEBUG

      #    #For Test purposes
      #    #fmail=[Inpath+"/mail_to_watch_test.txt",Inpath+"/mail_to_wning_test.txt",Inpath+"/mail_to_alert_test.txt"]

      #    #Default receiver
      #    # Thereceivers=['mangeard@udel.edu']
      #    Thereceivers=['default@example.com'] #DEBUG

      #    # print(df[-10:])

      #    #Last considered minute:
      #    LastStatus= df.iloc[-1].Status
      #    if LastStatus != 0:          #  the alarm level is not Quiet: Need to check previous minutes
      #       #Look for the starting minute of the alarm level
      #       i=1
      #       while df.iloc[-1-i].Status == LastStatus:
      #          i=i+1

      #       #Index J="-1-i" is the index of the last minute prior the current alarm level
      #       J=-1-i
      #       #Index J+1 is the first minute of the current alarm level
      #       if df.iloc[J+1].Status > df.iloc[J].Status:  #Check if an email has already been sent else don't send any
      #          #print("The start of the alarm level is a rise of alarm level. Checking if an email has already been sent")
      #          if df.iloc[J+1].Time > lastemails[Status[int(LastStatus)]]: #Email has not been sent yet
      #             #print(df.iloc[J].Status,df.iloc[J].Time)
      #             #print(df.iloc[J+1].Status,df.iloc[J+1].Time)
      #             #print(df.iloc[-1].Status,df.iloc[-1].Time)
      #             #print("Email has not been sent yet! Let's send it!")
      #             ###########################################################
      #             ###########################################################
      #             ###########################################################
      #             ###SEND EMAIL
      #             ###########################################################
      #             ###########################################################
      #             ###########################################################
      #             # print(df.info(verbose=True, show_counts=True))  #DEBUG
      #             # print("email starting")  #DEBUG

      #             # sys.exit() #DEBUG

      #             msg = EmailMessage()

      #             #Receivers: Add the mailing list corresponding to the alarm level
      #             Add_Emailreceivers(fmail[int(int(LastStatus))-1],Thereceivers)
      #             #subject: Simple and depend on the alarm level
      #             subject ="""Subject: gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[int(LastStatus)],df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"))
      #             subject2 ="""gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[int(LastStatus)],df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"))

      #             #subject ="""gle alarm ({0:s})""".format(Status[int(LastStatus)])

      #             #print(subject)

      #             #Body of the message
      #             #It depends of the alarm status and should include time, and stations above threshold
      #             #and the link to access the webpage with the plot
      #             body= "{0:s} (UT): {1:s} alarm\n".format(df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),Status[int(LastStatus)])
      #             body=body+"Rate increase(s):\n"
      #             # for i in range(N):
      #             for curIndex in stations.index:
      #                if stations.at[curIndex,'InAlert'] and df.iloc[J+1][curIndex+'F'] ==1:
      #                   body=body+"{0:s} ({1:s}): {2:s} (UT), {3:4.2f}%\n".format(stations.at[curIndex,'Labels'],curIndex,df.iloc[J+1].Time.strftime("%Y-%m-%d %H:%M:%S"),100.*(df.iloc[J+1][curIndex+'Ith']-1.))
      #             body=body+"{0:s}\n".format(urlalarm)

      #             print(Thereceivers)

      #             #Make message
      #             message=header+Bcc+subject+body
      #             #message=subject+body
      #             print(body)
      #             msg.set_content(body)
      #             # msg['From'] = 'GLE Alarm System <mangeard@udel.edu>'
      #             msg['From'] = 'GLE Alarm System <gle@example.com>' #DEBUG
      #             #msg['From'] = 'Pierre-Simon Mangeard <mangeard@udel.edu>'

      #             msg['To'] = Thereceivers[0]
      #             #msg['Bcc'] = 'mangeard@udel.edu,pierresimonmangeard@yahoo.fr,abydosp@yahoo.fr,psmangeard@gmail.com'
      #             msg['Bcc'] = ', '.join(Thereceivers[1:])

      #             msg['Subject'] = subject2

      #             print(msg)

      #             #Send the email
      #             print("Let's send an email")
      #             #print(message)
      #             df.iloc[-360:].to_csv('{0:s}/GLE_{1:s}_{2:s}.txt'.format(
      #                      Outpath,Status[int(LastStatus)],df.iloc[-1].Time.strftime("%Y%m%d_%H%M%S")),
      #                      sep=',',date_format='%y/%m/%d %H:%M:%S')


      #             # sys.exit() #DEBUG

      #             #smtpObj2 = smtplib.SMTP('localhost')
      #             """
      #             #DEBUG
      #             smtpObj2 = smtplib.SMTP('mail.udel.edu')
      #             smtpObj2.send_message(msg)
      #             smtpObj2.quit()

      #             """
      #             #try:
      #             #   smtpObj = smtplib.SMTP('localhost')
      #             #   smtpObj.sendmail(sender, Thereceivers, message)
      #             #   print ("Successfully sent email")
      #             #except:
      #             #    print ("Error: unable to send email")


      #             #SendEmail(senders,Thereceivers,message)

      #             ###########################################################
      #             #print("Let's update the file containing the time of the last emails!")
      #             lastemails[Status[int(LastStatus)]]=df.iloc[J+1].Time
      #             #print("New time of last email:",lastemails[Status[int(LastStatus)]])

      #             # print(lastemails) #DEBUG
      #             # sys.exit() #DEBUG

      # # if (not isReplay):
      #    #Format timestamp to time
         # for i in range(3):
         #       lastemails[Status[i+1]] =lastemails[Status[i+1]].strftime("%Y-%m-%d %H:%M:%S")
         #Save time when the last alarm emails were sent
         #print(lastemails)
         with open('./lastemails.json','w') as lastemailsjson:
            lastemailsjson.write(json.dumps(lastemails)) # use `json.loads` to do the reverse



      # for i in range(N):
      #   df=df.drop(columns=[nmdbtag[i]+'F'])

      ########################
      ### Kp index
      ########################

      #filename=Inpath+'/'+'Kp_prelim'
      #kp=pd.read_csv(filename, delim_whitespace=True)
      #kp['Time']=kp['yyyy'].astype(str)+'-'+kp['mo'].astype(str)+'-'+kp['dm'].astype(str)+' '+kp['HH'].astype(str)+':'+kp['MM'].astype(str)
      #kp['Time']=pd.to_datetime(kp['Time'],infer_datetime_format=True)
      #kp=kp.drop(columns=['yyyy','mo','dm','HH','MM','SS'])
      #kp.index = kp['Time']
      #print(kp.head())


      ########################
      ### Display
      ########################


      fontsize=17

      if(False): #DEBUG

         fig=plt.figure(figsize=(14, 11), dpi=80)

         axesT = fig.add_subplot(5,1,(2,3))
         ymax=30000.
         ymin=0.
         for i in range(N):
            axesT.plot(df['Time'],Fact[i]*df[nmdbtag[i]+'T'],'-',linewidth=0.8,label=r'{0:s} {1:s}'.format(Labels[i],sFact[i]))
            if df[nmdbtag[i]+'T'].max()>ymax: ymax=df[nmdbtag[i]+'T'].max()
            if df[nmdbtag[i]+'T'].min()<ymin: ymin=df[nmdbtag[i]+'T'].min()

         plt.tick_params(axis='x', which='major', labelsize=0,direction='in',length=6)
         plt.tick_params(axis='y', which='major', labelsize=fontsize,direction='in',length=6)
         plt.tick_params(axis='y', which='major', labelsize=fontsize,direction='in',length=6)

         axesT.xaxis.set_major_locator(mdates.HourLocator(interval=1))
         axesT.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))
         axesT.set_xlim(now - timedelta(hours=12),now)
         axesT.set_ylim(ymin,ymax-1)
         axesT.set_ylabel('Rate [count / minute]\n3-min moving average',fontsize=fontsize+1)

         plt.grid(axis='both',which='major',linewidth=0.5,linestyle=':',color='gray')

         plt.legend(bbox_to_anchor=(1.01,0.525), loc="center left", borderaxespad=0,
                  fontsize=fontsize,labelspacing=1,frameon=False)
         plt.title('GLE Alarm from Bartol Neutron Monitors - {0:s} {1:s} {2:s} UT'.format(now.strftime("%Y-%m-%d"),r'$@$',now.strftime("%H:%M:%S")),fontsize=fontsize)

         axes = fig.add_subplot(5,1,(4,5),sharex=axesT)
         ymax=10.
         ymin=-5.

         for i in range(N):
            axes.plot(df['Time'],100.*(df[nmdbtag[i]+'Ith']-1.),'-',linewidth=0.8,label=r'{0:s}'.format(Labels[i]))
            if df[nmdbtag[i]+'Ith'].isnull().values.any(): pass #print('Null values in {0:s} during plotting'.format(nmdbtag[i]+'Ith'))
            else:
               if 100.*(df[nmdbtag[i]+'Ith'].max()-1.)>ymax: ymax=100.*(df[nmdbtag[i]+'Ith'].max()-1.)
               if 100.*(df[nmdbtag[i]+'Ith'].min()-1.)<ymin: ymin=100.*(df[nmdbtag[i]+'Ith'].min()-1.)

         plt.tick_params(axis='x', which='major', labelsize=fontsize+1,direction='in',length=6)
         plt.tick_params(axis='y', which='major', labelsize=fontsize,direction='in',length=6)
         plt.tick_params(axis='y', which='major', labelsize=fontsize,direction='in',length=6)

         axes.xaxis.set_major_locator(mdates.HourLocator(interval=1))
         axes.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))
         ###axes.set_xlim(now - timedelta(hours=8),now)
         axes.set_ylim(ymin,ymax-0.001)
         axes.set_ylabel('Rate increase [%]\n(3-min tr. moving average)',fontsize=fontsize+1)
         axes.axhline(y=Level,linewidth=0.5,linestyle='-',color='red')

         plt.grid(axis='both',which='major',linewidth=0.5,linestyle=':',color='gray')
         plt.legend(bbox_to_anchor=(1.01,0.525), loc="center left", borderaxespad=0,
                  fontsize=fontsize,labelspacing=1,frameon=False)
         #plt.title('GLE Alarm from Bartol Neutron Monitors - Last update: {0:s} {1:s} {2:s} UT'.format(now.strftime("%Y-%m-%d"),r'$@$',now.strftime("%H:%M:%S")),fontsize=fontsize)

         axes.text(axes.get_xlim()[1] + 0.19*(axes.get_xlim()[1] -axes.get_xlim()[0] ) ,
                  axes.get_ylim()[0]+ 0.0*(axes.get_ylim()[1] -axes.get_ylim()[0] ),
                  Notused, horizontalalignment='left', fontsize=fontsize-2,zorder=10)


         axesal = fig.add_subplot(5,1,(1,1),sharex=axes)
         axesal.plot(df[df['Status']==3]['Time'],3*np.ones(len(df[df['Status']==3])),'o',color='red',label=Status[3])
         axesal.plot(df[df['Status']==2]['Time'],2*np.ones(len(df[df['Status']==2])),'o',color='orange',label=Status[2])
         axesal.plot(df[df['Status']==1]['Time'],1.*np.ones(len(df[df['Status']==1])),'o',color='blue',label=Status[1])
         axesal.plot(df[df['Status']==0]['Time'],0*np.ones(len(df[df['Status']==0])),'o',color='gray',label=Status[0])
         axesal.set_ylabel('Alarm Level',fontsize=fontsize+1)

         plt.tick_params(axis='x', which='major', labelsize=0,direction='in',length=6)
         plt.tick_params(axis='x', which='minor', labelsize=0,direction='in',length=3)
         plt.tick_params(axis='y', which='major', labelsize=fontsize,direction='in',length=6)
         plt.yticks(np.arange(0, 4, 1.0))

         axesal.xaxis.set_major_locator(mdates.HourLocator(interval=1))
         axesal.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))
         axesal.set_ylim(0,3.75)
         plt.grid(axis='x',which='major',linewidth=0.5,linestyle=':',color='gray')
         plt.legend(bbox_to_anchor=(1.01,0.48), loc="center left", borderaxespad=0,
                  fontsize=fontsize,labelspacing=1,frameon=False)

         axesal.text(axesal.get_xlim()[0] + 0.02*(axesal.get_xlim()[1] -axesal.get_xlim()[0] ) ,
                  axesal.get_ylim()[1]- 0.12*(axesal.get_ylim()[1] -axesal.get_ylim()[0] ),
                  "Current: ", horizontalalignment='left', fontsize=fontsize+1,zorder=10)

         axesal.text(axesal.get_xlim()[0] + 0.11*(axesal.get_xlim()[1] -axesal.get_xlim()[0] ) ,
                  axesal.get_ylim()[1]- 0.12*(axesal.get_ylim()[1] -axesal.get_ylim()[0] ),
                  "{0:s}".format(Status[int(LastStatus)]), horizontalalignment='left',color=Statuscol[int(LastStatus)], fontsize=fontsize+1,zorder=10)


         axesal.text(axesal.get_xlim()[0], axesal.get_ylim()[1]+ 0.017*(axesal.get_ylim()[1] -axesal.get_ylim()[0] ),
               'Last update: {0:s} {1:s} {2:s} UT'.format(now.strftime("%Y-%m-%d"),r'$@$',now.strftime("%H:%M:%S")),fontsize=fontsize+1,horizontalalignment='left')


         plt.subplots_adjust(left=0.1, bottom=0.06, right=0.8, top=0.95, wspace=0, hspace=0.00)

         fig.savefig('{0:s}/Graphs/GLE_Alarm.png'.format(Outpath))


         #for i in range(N-1):
         #   df=df.drop(columns=[nmdbtag[i+1]+'T'])
         #   df=df.drop(columns=[nmdbtag[i+1]+'Ith'])
         #   df=df.drop(columns=[nmdbtag[i+1]])

         #print(df.iloc[-10:])
         #print("--- %s seconds ---" % (time.time() - start_exetime))

         # plt.show()
         plt.close()

      if isReplay:
         if (23==now.hour) and (59==now.minute):
            # print(earliestBaselineTime)  #DEBUG
            if (now.day==earliestBaselineTime.day): #check if baseline is different day
               dfToDel = df
               df=df.iloc[-(24*60):].copy() #discard history prior to this day
               del dfToDel
               gc.collect()
            if dailyDump:
               # df.to_csv('{0:s}/Day/GLE_Day_{1:s}.csv'.format(
               #             LocalOutpath,df.index[-1].strftime("%Y%m%d")),
               #             sep=',',date_format='%y/%m/%d %H:%M:%S')
               df.to_csv('{0:s}/Day/GLE_Day_{1:s}.csv'.format(
                           Outpath,df.index[-1].strftime("%Y%m%d")),
                           sep=',',index=True,date_format='%Y-%m-%dT%H:%M:%SZ')

               if not isProduction :
                  print('Wrote {0:s}/Day/GLE_Day_{1:s}.csv'.format(
                           LocalOutpath,df.index[-1].strftime("%Y%m%d"))) #DEBUG

         now+=timedelta(minutes=1)
         if 0==len(archive_data) :
            if now > replayEnd:
               print("NO ARCHIVE DATA LEFT") #DEBUG
               print(df.info(verbose=True, show_counts=True))  #DEBUG
               break #ends the while loop
            else:
               monthRowSkip=1
               if not ((replayEnd.year == now.year) and (replayEnd.month == now.month)) :
                  if 12 == now.month :
                     replayRows = (24*60)*(date(year=now.year+1,month=1,day=1)-now.date()).days
                  else :
                     replayRows = (24*60)*(date(year=now.year,month=now.month+1,day=1)-now.date()).days

               else:
                  # replayRows = (24*60)*(replayEnd-now).days #replay 24 hours and included
                  # print(replayEnd-now) #DEBUG
                  replayRows = 1 + ((replayEnd-now).total_seconds()/60) #replay 24 hours and included

               # print(replayRows) #DEBUG
               # sys.exit() #DEBUG
               # for i in range(N):
               for curIndex in stations.index:
                  try:
                     new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, curIndex, now.year, now.month), names=['Date', 'Time', '{0:s}'.format(curIndex),  '{0:s}_P'.format(curIndex), 'DELETEuncorr'], skiprows=monthRowSkip, nrows=replayRows, sep='\s+')
                     # print(new_archive_data)  #DEBUG
                     if new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max() > 1.0:
                        print('Archive data for {0:s} has greater than 1 min time delta between samples'.format(stations.at[curIndex,'Labels']))
                        raise ValueError
                     if len(new_archive_data) < replayRows:
                        print('Archive data for {0:s} not long enough for replay'.format( stations.at[curIndex,'Labels']))
                        raise ValueError

                  except Exception as err:
                     print('Exception {0} occured. {1:s} will be excluded from alert and filler data <{2}> will be used'.format(type(err), stations.at[curIndex,'Labels'], fillerData))
                     # InAlert[i]=0
                     stations.at[curIndex,'InAlert']=False
                     if stations.index.values[0]==curIndex:
                        if not ((replayEnd.year == now.year) and (replayEnd.month == now.month)) :
                           if 12 == now.month :
                              archive_data = pd.DataFrame({ 'Time': pd.date_range(start=now, end="{0:s}-31 23:59+0000".format(now.strftime("%Y-%m")),freq='1min')})
                           else :
                              archive_data = pd.DataFrame({ 'Time': pd.date_range(start=now, end=(datetime(year=now.year, month=now.month+1, day=1, hour=0, minute=0, second=0, tzinfo=timezone.utc)-timedelta(minutes=1)),freq='1min')})
                        else :
                           archive_data = pd.DataFrame({ 'Time': pd.date_range(start=now, end=replayEnd,freq='1min')})

                        # archive_data = pd.DataFrame({ 'Time': pd.date_range(start=start, end="{0:s} 23:59".format(now.strftime("%Y-%m-%d")),freq='1min')})
                        archive_data.index = archive_data['Time']
                        archive_data=archive_data.drop(columns=['Time'])
                        # print(archive_data)  #DEBUG
                     archive_data['{0:s}'.format(curIndex)]=fillerData
                     archive_data['{0:s}_P'.format(curIndex)]=fillerData
                  else:
                     if not isProduction : print(new_archive_data.info(verbose=True, show_counts=True)) #DEBUG
                     # print(new_archive_data)  #DEBUG
                     new_archive_data['Time'] = new_archive_data.apply(lambda r: pd.Timestamp.combine(datetime.strptime(r['Date'], '%Y-%m-%d').date(), datetime.strptime(r['Time'], '%H:%M:%S').time()).tz_localize(timezone.utc), axis=1)
                     new_archive_data.index = new_archive_data['Time']
                     new_archive_data=new_archive_data.drop(columns=['DELETEuncorr'])
                     new_archive_data=new_archive_data.drop(columns=['Date'])
                     new_archive_data=new_archive_data.drop(columns=['Time'])
                     if stations.index.values[0]==curIndex:
                        archive_data = new_archive_data
                     else:
                        archive_data = archive_data.join(new_archive_data, how='left')

               archive_data = archive_data.mask(0.0==archive_data) #Make 0.0 values NaN

               #print(df.info(verbose=True, show_counts=True)) #DEBUG
               # print('archive_data') #DEBUG
               # print(archive_data.info(verbose=True, show_counts=True)) #DEBUG


         # print("now =", now) #DEBUG
         end = now.strftime("%Y-%m-%d %H:%M")

         # startdt = now - timedelta(hours=initHours)
         # start= startdt.strftime("%Y-%m-%d %H:%M")
         # print(df[-2:])  #DEBUG
         # print(archive_data.iloc[0])  #DEBUG
         # print(archive_data[:end])  #DEBUG
         # print('concat')  #DEBUG
         df=pd.concat([df, archive_data[:end]])
         # df['Time'][-1]=end
         # print(df[-2:])  #DEBUG
         # df.iloc[-1]['Time']=end
         df.at[df.last_valid_index(),'Time']=end
         # df['Time'].iloc[-1]=end
         # print(df.info(verbose=True, show_counts=True)) #DEBUG


         archive_data=archive_data[1:]

         # print(df.info(verbose=True, show_counts=True))  #DEBUG
         #print(df[-2:])  #DEBUG
         # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
         # if LastStatus<3 :
         # if (df.tail(2)['Status'].max()) < 3 :
         if (df.tail(2)['Status'].fillna(0).max()) < 3 :
            # stations['BaselineTime']=df.index[-T0]
            stations['BaselineTime']=df.last_valid_index() - timedelta(minutes=T0)
            # print('At {0} moved to baseline {1}'.format(now,stations.at[stations.first_valid_index(),'BaselineTime']))
         else:
            if not isProduction : print('At {0} holding baseline {1}'.format(now,stations.at[stations.first_valid_index(),'BaselineTime']))
         # sys.exit() #DEBUG
      else :
         if dfFuture is not None and not dfFuture.empty:
            df = pd.concat([df, dfFuture.head(1)])
            dfFuture.drop(dfFuture.index[0], inplace=True)
            now = df.last_valid_index() #TODO rerun starting at first update
            if not isProduction : print(now, " added")  #DEBUG



            if not isProduction : print(dfFuture.info(verbose=True, show_counts=True))  #DEBUG
            if not isProduction : print(df.info(verbose=True, show_counts=True))  #DEBUG

            # dfFuture = None 
            
         else :
            # print(df.info(verbose=True, show_counts=True))  #DEBUG
            # dfgle=df.loc[startdt:]
            dfgle=df[df.index > startdt]
            # dfgle=df#.copy(deep=True)
            # print(dfgle.info(verbose=True, show_counts=True))  #DEBUG
            # print(list(dfgle.filter(regex='.+Tb?$').columns))  #DEBUG
            dfgle=dfgle.drop(columns=list(dfgle.filter(regex='.+Tb?$').columns))
            dfgle=dfgle.drop(columns=['Time'])
            # print(dfgle.info(verbose=True, show_counts=True))  #DEBUG
            # dfgle=dfgle.replace(0, np.nan)
            # dfgle=dfgle.dropna()
            # dfgle = dfgle.drop_duplicates()
            # dfgle = dfgle.drop_duplicates(subset=['Day_tag','Time_tag'], keep=False)
            # print(dfgle.info(verbose=True, show_counts=True))  #DEBUG
            for modIndex in modFileStations :
               dfst = dfgle[modIndex + 'Ith']
               # dfgle.to_csv('{0:s}/GLE_Alarm_2days.txt'.format(LocalOutpath),sep=' ',index=True,date_format='%y/%m/%d %H:%M:%S',
               #                               # header=['YYYY-MM-DD','hh:mm:ss','corr','press','uncorr'],
               #                               float_format='%.2f',na_rep='0.')
               dfst.to_csv('{0:s}/data/{1:s}/increase/2days/{2:s}_2days.{1:s}'.format(Outpath,'txt',modIndex),sep=' ',index=True,date_format='%Y-%m-%dT%H:%M:%SZ',
                                             float_format='%.4f',na_rep='0.')
               dfst.to_csv('{0:s}/data/{1:s}/increase/2days/{2:s}_2days.{1:s}'.format(Outpath,'csv',modIndex),sep=',',index=True,date_format='%Y-%m-%dT%H:%M:%SZ',
                                             float_format='%.4f',na_rep='0.')
               dfst.to_json('{0:s}/data/{1:s}/increase/2days/{2:s}_2days.{1:s}'.format(Outpath,'json',modIndex),date_format='iso',date_unit='s')

            # for modIndex in modFileStations :
            #    # dfst = dfgle[[modIndex,modIndex + '_P']]
            #    # dfst = dfgle['{0:s}'.format(modIndex)]
            #    dfst = dfgle[str(modIndex+'_P')]
            #    # dfgle.to_csv('{0:s}/GLE_Alarm_2days.txt'.format(LocalOutpath),sep=' ',index=True,date_format='%y/%m/%d %H:%M:%S',
            #    #                               # header=['YYYY-MM-DD','hh:mm:ss','corr','press','uncorr'],
            #    #                               float_format='%.2f',na_rep='0.')
            #    dfst.to_csv('{0:s}/data/{1:s}/rates/2days/{2:s}_2days.{1:s}'.format(Outpath,'txt',modIndex),sep=' ',index=True,date_format='%Y-%m-%dT%H:%M:%SZ',
            #                                  float_format='%.2f',na_rep='0.')
            #    dfst.to_csv('{0:s}/data/{1:s}/rates/2days/{2:s}_2days.{1:s}'.format(Outpath,'csv',modIndex),sep=',',index=True,date_format='%Y-%m-%dT%H:%M:%SZ',
            #                                  float_format='%.2f',na_rep='0.')
            #    dfst.to_json('{0:s}/data/{1:s}/rates/2days/{2:s}_2days.{1:s}'.format(Outpath,'json',modIndex),date_format='iso',date_unit='s')


            #Write into a sqlite file:
            # Create your connection.

            dfgle['Tunix']= (dfgle.index - pd.Timestamp("1970-01-01", tz='UTC')) / pd.Timedelta('1s')
            # dfgle=dfgle.drop(columns=['Day_tag','Time_tag'])
            # dfgle['LDVL'] = 1.0  #DEBUG
            # dfgle['LDVLIth'] = 1.0  #DEBUG

            cnx = sqlite3.connect('{0:s}/GLE_Alarm_2days.db'.format(LocalOutpath))
            dfgle.to_sql(name='GLEAlarm', con=cnx,if_exists='replace')
            cnx.close()
            archive_data = []
            while(len(archive_data) < 1):
               listNewModFiles=[]
               delayTime = datetime.now(timezone.utc) - timedelta(minutes=Ndelay)
               delayTime = delayTime.replace(second = 0, microsecond = 0)
               updateWindowStart = df.last_valid_index() - timedelta(minutes=updateWindowMinutes)
               if not isProduction : print('Updates between ', updateWindowStart, ' : ', delayTime)  #DEBUG

               
               while(len(listNewModFiles) < 1):
                  # time.sleep(20)
                  # listNewModFiles=[]
                  # print(stations['ModTime'])  #DEBUG

                  for modIndex in modFileStations :
                     if os.path.isfile(Inpath+modIndex+'_2days.txt'):
                        newMtime = os.path.getmtime(Inpath+modIndex+'_2days.txt')
                        if newMtime != stations.at[modIndex,'ModTime'] :
                           # print(stations.at[modIndex,'ModTime'])  #DEBUG
                           # print(modIndex)  #DEBUG
                           # print(newMtime)  #DEBUG
                           stations.at[modIndex,'ModTime'] = newMtime
                           listNewModFiles.append(modIndex)
                  if(len(listNewModFiles) < 1) :
                     time.sleep(20)
               # print(listNewModFiles)
               # now+=timedelta(minutes=1)
               for curIndex in listNewModFiles:
                  try:
                     # raw_data.append(pd.read_json(Inpath+'/'+nm[i]+'_ql_l'+str(Ndays)+'d_1min.json'))
                     # raw_data[-1]['Time'] =pd.to_datetime(raw_data[-1]['Time'],infer_datetime_format=True)
                     # raw_data[-1]['Time'] = raw_data[-1]['Time'].dt.tz_localize(None)
                     # raw_data[-1].index = raw_data[-1]['Time']
                     # raw_data[-1]=raw_data[-1].drop(columns=['Time'])
                     # raw_data[-1].to_csv('{0:s}/GLE_Alarm_{1:s}.txt'.format(Outpath,nm[i]), sep=',',date_format='%y/%m/%d %H:%M:%S')
                     # print(Inpath+curIndex+'_30days.txt') #DEBUG
                     new_archive_data = pd.read_csv(Inpath+curIndex+'_2days.txt', names=['Date', 'Time', '{0:s}'.format(curIndex),  '{0:s}_P'.format(curIndex), 'DELETEuncorr'], skiprows=monthRowSkip, sep='\s+')
                     # print(new_archive_data) #DEBUG
                     # print(new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max()) #DEBUG

                     # if new_archive_data['Time'].apply(lambda r: int(r[3:5])).diff().max() > 1.0:
                     #    print('Archive data for {0:s} has greater than 1 min time delta between samples'.format(stations.at[curIndex,'Labels']))
                     #    # raise ValueError
                     # if len(new_archive_data) < replayRows:
                     #    print('Archive data for {0:s} not long enough for replay'.format(stations.at[curIndex,'Labels']))
                     #    raise ValueError

                     # new_archive_data['Time'] = new_archive_data['Time'].dt.tz_localize(None)


                  except Exception as err:
                     if not isProduction : print('Exception {0} occured. {1:s} will be excluded from alert and filler data <{2}> will be used'.format(type(err), stations.at[curIndex,'Labels'], fillerData))
                     # stations.at[curIndex,'InAlert']=False #TODO modify something other than InAlert
                     # if listNewModFiles[0]==curIndex:
                     #    if not ((replayEnd.year == replayStart.year) and (replayEnd.month == replayStart.month)):
                     #       if 12 == replayStart.month :
                     #          archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end="{0:s}-31 23:59+0000".format(replayStart.strftime("%Y-%m")),freq='1min')})
                     #       else :
                     #          archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end=(datetime(year=replayStart.year, month=replayStart.month+1, day=1, hour=0, minute=0, second=0, tzinfo=timezone.utc)-timedelta(minutes=1)),freq='1min')})
                     #    else :
                     #       archive_data = pd.DataFrame({ 'Time': pd.date_range(start=startdt, end=replayEnd,freq='1min')})
                     #    archive_data.index = archive_data['Time']
                     #    archive_data=archive_data.drop(columns=['Time'])


                     # archive_data['{0:s}'.format(curIndex)]=fillerData
                     # archive_data['{0:s}_P'.format(curIndex)]=fillerData
                  else:
                     try :
                        new_archive_data = new_archive_data.tail(updateWindowMinutes+Ndelay)
                        new_archive_data['Time'] = new_archive_data.apply(lambda r: pd.Timestamp.combine(datetime.strptime(r['Date'], '%Y-%m-%d').date(), datetime.strptime(r['Time'], '%H:%M:%S').time()).tz_localize(timezone.utc), axis=1)
                        new_archive_data.index = new_archive_data['Time']


                        # stations.at[curIndex,'ModTime']=os.path.getmtime(Inpath+curIndex+'_30days.txt')
                        # print(stations.loc[curIndex])  #DEBUG



                        # # Filter for current month to produce NMDB formatted file
                        # new_archive_data_nmdb = new_archive_data[new_archive_data.index.month == now.month]

                        # # Resample to 1-minute frequency and fill missing values with NaN
                        # # new_archive_data_nmdb = new_archive_data_nmdb.resample('1min').asfreq()
                        # full_month_index = pd.date_range(start=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end=now, freq='min')
                        # new_archive_data_nmdb = new_archive_data_nmdb.reindex(full_month_index)

                        # # Restore original column order (all columns)
                        # new_archive_data_nmdb = new_archive_data_nmdb.rename(columns={'Date': 'YYYY-MM-DD', 'Time': 'hh:mm:ss', '{0:s}'.format(curIndex): 'corr', '{0:s}_P'.format(curIndex): 'press', 'DELETEuncorr': 'uncorr'})
                        # new_archive_data_nmdb['YYYY-MM-DD'] = new_archive_data_nmdb.index.strftime('%Y-%m-%d')
                        # new_archive_data_nmdb['hh:mm:ss'] = new_archive_data_nmdb.index.strftime('%H:%M:%S')
                        # new_archive_data_nmdb = new_archive_data_nmdb.fillna(0.0)


                        # # Save with original header format
                        # output_file_nmdb = '{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format('/home/lucasb/genNMDB/', curIndex, now.year, now.month)
                        # new_archive_data_nmdb.to_csv(output_file_nmdb, sep=' ', index=False, float_format='%.2f')

                        # print(f"Saved: {output_file_nmdb}")

                        new_archive_data=new_archive_data.drop(columns=['DELETEuncorr'])
                        new_archive_data=new_archive_data.drop(columns=['Date'])
                        new_archive_data=new_archive_data.drop(columns=['Time'])

                        # print(new_archive_data) #DEBUG
                        # print(new_archive_data.ne(df.tail(updateWindowMinutes)[new_archive_data.columns]).any(axis=1)) #DEBUG

                        # new_archive_data=new_archive_data[new_archive_data.index > df.last_valid_index()]
                     except Exception as err:
                        if not isProduction : print('Exception {0} occured. {1:s} update data not used'.format(type(err), stations.at[curIndex,'Labels']))
                        stations.at[curIndex,'ModTime'] = 0 #force reread
                     else:
                        # delayTime = datetime.now(timezone.utc) - timedelta(minutes=Ndelay)
                        # delayTime = delayTime.replace(second = 0, microsecond = 0)
                        if ((updateWindowStart - new_archive_data.first_valid_index()).total_seconds() / timedelta(minutes=1).total_seconds()) > 0 :
                           # if ((new_archive_data.last_valid_index() - delayTime).total_seconds() / timedelta(minutes=1).total_seconds()) > 0 :
                           #TODO make sure it rereads later
                           if not isProduction : print('Update before window')  #DEBUG
                           if not isProduction : print(new_archive_data)  #DEBUG
                           #   new_archive_data=new_archive_data.loc[new_archive_data.index.isin([delayTime])]
                           new_archive_data=new_archive_data.loc[updateWindowStart:delayTime]
                           if not isProduction : print(new_archive_data)  #DEBUG
                        else :
                           new_archive_data=new_archive_data.loc[updateWindowStart:delayTime]
                           # new_archive_data=new_archive_data.tail(5)
                           # print(new_archive_data)  #DEBUG
                           # print(new_archive_data.info(verbose=True, show_counts=True))  #DEBUG
                           # print(df.last_valid_index())

                        if (len(archive_data) < 1):
                           # archive_data = new_archive_data
                           # print(Fulldf)  #DEBUG
                           # print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG
                           # archive_data = Fulldf.join(new_archive_data, how='left')
                           archive_data = new_archive_data

                        else:
                           archive_data = archive_data.join(new_archive_data, how='left')

                        # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
                        # print(df.last_valid_index())

                        # sys.exit() #DEBUG
               if not isProduction : print(listNewModFiles)  #DEBUG
               # print(archive_data.ne(df.tail(updateWindowMinutes)[archive_data.columns]).any(axis=1)) #DEBUG
            # if (len(archive_data.index) > (updateWindowMinutes + Ndelay)) :
               # archive_data = archive_data.tail(updateWindowMinutes + Ndelay)
               # archive_dataNans = archive_data.isna().any()
               # print("NAN Map")  #DEBUG
               # print(archive_dataNans)  #DEBUG

            if (len(archive_data.index) < 1) : #TODO consider nesting this futher in
               if not isProduction : print("No valid update data") #DEBUG
               for nanIndex in listNewModFiles :
                  stations.at[nanIndex,'ModTime'] = 0 #force reread

            else :
               for nanIndex in listNewModFiles :
                  if (nanIndex not in archive_data.columns) :
                     if not isProduction : print("No valid update data for ", nanIndex) #DEBUG
                     stations.at[nanIndex,'ModTime'] = 0 #force reread
                  elif np.isnan((archive_data.at[archive_data.last_valid_index(), nanIndex])) :
                     # print(archive_data.tail(1))  #DEBUG
                     stations.at[nanIndex,'ModTime'] = 0 #force reread

               

               if not isProduction : print(archive_data) #DEBUG
               newestDataMinDelta = (archive_data.last_valid_index() - df.last_valid_index()).total_seconds() / timedelta(minutes=1).total_seconds()
               if not isProduction : print(newestDataMinDelta) #DEBUG

               
               idxInter = df.index.intersection(archive_data.index)

               dfInter = df.loc[idxInter]
               if not isProduction : print(dfInter) #DEBUG
               archive_dataInter = archive_data.loc[idxInter]
               if not isProduction : print(archive_dataInter) #DEBUG

               changed_mask = archive_dataInter.notna() & dfInter.ne(archive_dataInter)

               # changed_rows = dfInter[changed_mask.any(axis=1)]

               row_changed = changed_mask.any(axis=1)
               rerunTime = row_changed.idxmax() if row_changed.any() else None
               if not isProduction : print("rerunTime = ",rerunTime) #DEBUG

               if rerunTime : 
                  rerunDataMinDelta = (rerunTime - df.last_valid_index()).total_seconds() / timedelta(minutes=1).total_seconds()

                  if not isProduction : print('dfInter columns before update = ', dfInter.loc[dfInter.index, archive_dataInter.columns]) #DEBUG
                  dfInter.update(archive_dataInter)
                  if not isProduction : print('dfInter columns after update = ', dfInter.loc[dfInter.index, archive_dataInter.columns]) #DEBUG




               # if (newestDataMinDelta > 1) :
               #    # print(df.first_valid_index())  #DEBUG
               #    if not isProduction : print(archive_data.last_valid_index() - timedelta(minutes=1))  #DEBUG
               #    # print(df.first_valid_index().tzinfo)  #DEBUG
               #    # print(archive_data.last_valid_index().tzinfo)  #DEBUG
               #    df=df.reindex(pd.date_range(start=df.first_valid_index(), end=archive_data.last_valid_index() - timedelta(minutes=1), freq='1min'))
               #    df=pd.concat([df, archive_data.tail(1)])
               #    # now+=timedelta(minutes=1)
               #    now = df.last_valid_index() 
               #    startdt += timedelta(minutes=int(newestDataMinDelta))
               # elif (newestDataMinDelta > 0) :
               # # if (archive_data.last_valid_index() > df.last_valid_index()) :
               #    # df=pd.concat([df, archive_data.head(1)])
               #    df=pd.concat([df, archive_data.tail(1)])
               #    # now+=timedelta(minutes=1)
               #    now = df.last_valid_index()
               #    startdt += timedelta(minutes=1)
               # elif (0.0 == newestDataMinDelta ):
               #    # print(df.tail(1)[archive_data.columns]) #DEBUG
               #    # df = df.update(archive_data)
               #    for curCol in archive_data.columns :
               #       df.at[df.last_valid_index(),curCol] = archive_data.loc[archive_data.last_valid_index(),curCol]
               # else :
               #    if not isProduction : print("Data too old") #DEBUG
               

               if (newestDataMinDelta > 0) :
                  df=pd.concat([df, archive_data.tail(int(newestDataMinDelta))])
                  if rerunTime :
                     df.update(archive_data)
                     if not isProduction : print('df update + new rows = ', df.loc[rerunTime:, archive_data.columns]) #DEBUG
                     dfFuture = df.loc[rerunTime + (timedelta(minutes=1)):]
                     if not isProduction : print(dfFuture.info(verbose=True, show_counts=True))  #DEBUG
                     df = df.loc[:rerunTime]
                     startdt += timedelta(minutes=int(rerunDataMinDelta))
                     if (df.tail(2)['Status'].fillna(0).max()) > 2 :
                        #find latest consecutive non Alert minutes
                        df['temp2NoAlert'] = df['Status'] < 3
                        df['temp2NoAlert'] = df['temp2NoAlert'] & df['temp2NoAlert'].shift(1)
                        stations['BaselineTime']=df[df['temp2NoAlert'] == True].last_valid_index() - timedelta(minutes=(T0-1))
                        if not isProduction : print("New now is during Alert, Baseline moved back to :", df[df['temp2NoAlert'] == True].last_valid_index() - timedelta(minutes=(T0-1)))  #DEBUG
                        df = df.drop(columns=['temp2NoAlert'])

                  else :
                     startdt += timedelta(minutes=int(newestDataMinDelta))
                     if not isProduction : print('df new rows = ', df.tail(int(newestDataMinDelta))) #DEBUG
                  now = df.last_valid_index() 
                  
                  LastStatus = df.iloc[-2]['Status']
               elif rerunTime :
                  df.update(archive_data)

                  if not isProduction : print('df update = ', df.loc[rerunTime:, archive_data.columns]) #DEBUG
                  dfFuture = df.loc[rerunTime + (timedelta(minutes=1)):]
                  # if not isProduction : print(dfFuture.info(verbose=True, show_counts=True))  #DEBUG
                  df = df.loc[:rerunTime]
                  now = df.last_valid_index() 
                  LastStatus = df.iloc[-2]['Status']
                  if (df.tail(2)['Status'].fillna(0).max()) > 2 :
                     #find latest consecutive non Alert minutes
                     df['temp2NoAlert'] = df['Status'] < 3
                     df['temp2NoAlert'] = df['temp2NoAlert'] & df['temp2NoAlert'].shift(1)
                     stations['BaselineTime']=df[df['temp2NoAlert'] == True].last_valid_index() - timedelta(minutes=(T0-1))
                     if not isProduction : print("New now is during Alert, Baseline moved back to :", df[df['temp2NoAlert'] == True].last_valid_index() - timedelta(minutes=(T0-1)))  #DEBUG
                     df = df.drop(columns=['temp2NoAlert'])

               else :
                  #TODO process old out of window rates possibly without updating alarm
                  if not isProduction : print('df no update') #DEBUG
               # dfFuture = None #TODO rerun starting at first update





      # if LastStatus<3 :
      # if not isProduction : print('Last 2 status', df.tail(2)['Status'].max(), df.tail(2)['Status']) #DEBUG
      # if (df.tail(2)['Status'].max()) < 3 :
      if (df.tail(2)['Status'].fillna(0).max()) < 3 :
         # stations['BaselineTime']=df.index[-T0]
         stations['BaselineTime']=df.last_valid_index() - timedelta(minutes=T0)
         # print('At {0} moved to baseline {1}'.format(now,stations.at[stations.first_valid_index(),'BaselineTime']))
      else:
         if not isProduction : print('At {0} holding baseline {1}'.format(now,stations.at[stations.first_valid_index(),'BaselineTime']))

         # print(df.tail(1)) #DEBUG
      if not isProduction : print(now) #DEBUG
      if (0==now.hour) and (0==now.minute) and (dfFuture is None or dfFuture.empty):
      # print(earliestBaselineTime)  #DEBUG
         baselineDayDelta = (now - earliestBaselineTime).total_seconds() / timedelta(days=1).total_seconds()

         # if (now.day==earliestBaselineTime.day): #check if baseline is less than 3 days back
         if (baselineDayDelta < 2): #check if baseline is less than 2 days back
            dfToDel = df
            df=df.iloc[-((48*60)+1):].copy() #discard history prior to 2 days and current min
            del dfToDel
            gc.collect()
         if dailyDump:
            # df.to_csv('{0:s}/Day/GLE_Day_{1:s}.csv'.format(
            #             LocalOutpath,df.index[-1].strftime("%Y%m%d")),
            #             sep=',',date_format='%y/%m/%d %H:%M:%S')
            df.iloc[-((24*60)+1):-1].to_csv('{0:s}/Day/GLE_Day_{1:s}.csv'.format(
                        Outpath,df.index[-2].strftime("%Y%m%d")),
                        sep=',',index=True,date_format='%Y-%m-%dT%H:%M:%SZ')

            if not isProduction :
               print('Wrote {0:s}/Day/GLE_Day_{1:s}.csv'.format(
                        Outpath,df.index[-1].strftime("%Y%m%d"))) #DEBUG
   # print(df.info(verbose=True, show_counts=True))  #DEBUG

   # raw_data = archive_data.drop(columns=['Time'])
   # print(archive_data)  #DEBUG
   # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
   # sys.exit() #DEBUG

   # print(stations)  #DEBUG


   # break #not a replay so end


if __name__ == "__main__":
   main(sys.argv[1:])



#END
