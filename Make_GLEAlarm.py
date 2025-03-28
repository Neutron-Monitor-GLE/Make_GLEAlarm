#!/usr/bin/python3

"""
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

import os.path
from os import path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import ScalarFormatter
from matplotlib.cbook import get_sample_data
import matplotlib.gridspec as gridspec

import smtplib
from email.message import EmailMessage

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

def Add_Emailreceivers(filename,receivers):
   print ("Error: Skipping receivers from {filename} for development") #DEBUG
""" 
   with open(filename, "r") as filestream:
      for line in filestream:
         line=line.rstrip('\n') #Clean end \n (sometimes needed)
         currentline = line.split(",")
         if len(currentline)>0: #Clean empty line
            for i in range(len(currentline)):
               if currentline[i]:#remove empty string
                  receivers.append(currentline[i])  

 """
def SendEmail(senders,receivers,message):
   print ("Error: Skipping sending email to: {receivers} from: {senders} for development") #DEBUG
"""    
   try:
      smtpObj = smtplib.SMTP('localhost')
      smtpObj.sendmail(sender, receivers, message)         
      print ("Successfully sent email")
   except:
      print ("Error: unable to send email")   
       """

def main(argv):
   start_exetime = time.time()

   ########################
   ### DEFINE VARIABLES
   ########################
   Inpath = '.'      #input path
   #Inpath='d:/Documents/BartolData/ql'
   Outpath = '.'     #output path
   #Outpath='d:/Documents/BartolData/ql'
   Archivepath = '/home/lucasb/Archive/'     #archive path TODO add as arg
   isReplay = False #flag for replay functionality
   replayStart = date.today() #flag for replay functionality
   dailyDump = False #flag to dump data to file daily
   Ndelay = 3        #Number of minutes of delay
   #urlalarm="http://www.bartol.udel.edu/~takao/neutronm/glealarm/index.html"
   # urlalarm="https://neutronm.bartol.udel.edu/~mangeard/glealarm/GLE_Alarm.png"
   urlalarm="./GLE_Alarm.png" #DEBUG
   ########################
   ### ARGUMENTS
   ########################

   strinfo='Make_GLEAlarm.py: options:\n'
   strinfo=strinfo+'-n <Number of minutes of delay> \n'
   strinfo=strinfo+'-i <input path>\n'
   strinfo=strinfo+'-o <output path> (output path is the same as input path if not given)\n'
   strinfo=strinfo+'-r <replay day> (in valid ISO 8601 format like YYYY-MM-DD)\n'
   strinfo=strinfo+'-d (flag to dump all data to GLE_Day file daily)\n'
   
   try:
      opts, args = getopt.getopt(argv,"hn:i:o:r:d")
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
      elif opt in ("-o"):
         Outpath = arg     #output path
      elif opt in ("-r"):
         isReplay = True #flag to turn on replay functionality
         replayStart = date.fromisoformat(arg) #set the start day
         print("{0:s} interpreted Replay Day {1:s}".format(arg, replayStart.strftime("%D")))
      elif opt in ("-d"):
         dailyDump = True #flag to dump data to file daily

   if len(opts) <  1:
      print('For information: Make_GLEAlarm.py -h')
      sys.exit(2)
   
   ########################
   #Data frame all minutes and hours of the last 15 days
   ########################

   # datetime object containing current date and time
   now = datetime.now(timezone.utc) - timedelta(minutes=Ndelay)
   if isReplay: 
      now=datetime(year=replayStart.year, month=replayStart.month, day=replayStart.day, hour=0, minute=0, second=0, tzinfo=timezone.utc) #set to beginning of replay
   print("now =", now) #DEBUG
   end = now.strftime("%Y-%m-%d %H:%M")

   #Read json files that contain 10 days
   Ndays=10

   startdt = now - timedelta(hours=14)
   start= startdt.strftime("%Y-%m-%d %H:%M")

   # print("date and time =", start) #DEBUG
   print("date and time =", end) #DEBUG

   #Define full Ndays days data frame for count rates (minute rate)
   rng=pd.date_range(start=start, end=end,freq='1min')
   Fulldf = pd.DataFrame({ 'Time': rng}) 
   Fulldf.index = Fulldf['Time']
   # print(Fulldf)  #DEBUG

   ########################
   ### Stations to read
   ########################

   nm=      ['in','fs','pe','na','ne','th','sp','sp','mc','jb']
   nmdbtag= ['INVK','FSMT','PWNK','NAIN','NEWK','THUL','SOPO','SOPB','MCMU','JBGO']
   Labels=  ['Inuvik','Fort Smith','Peawanuck','Nain','Newark','Thule','South Pole','$^{\dagger}$South Pole - bare','McMurdo','Jang Bogo']
   InAlert= [1       ,1           ,1          ,1     ,0       ,1      ,1                       ,0                  ,1        ,0          ]
   sFact= ['','',' *2','',' *2','',' /2','','','']
   Fact=  [1.,1.,2.   ,1.,2.    ,1.,0.5 ,1.,1.,1.]

   #History from Makejson_ql.py
   #History= [0.597135,(0.598/0.94696),1.35333,0.59686,0.54518,0.57732*0.6,0.705,0.52308,0.52308]
   History= [0.597135,0.598,1.35333,0.59686,0.54518,0.57732*0.6,0.52308,0.52308,0.705]
   History=np.array(History)
   History=History/0.6
   #Number of stations
   N= len(nm)-1
   #if isReplay: N-=1 #DEBUG
   Notused='$^{\dagger}$Not used'

   raw_data=[]
   archive_data=[]
   if isReplay: 
      lastemails = {'Watch': datetime.strptime('1956-01-01 00:00:00', "%Y-%m-%d %H:%M:%S"), 'Warning': datetime.strptime('1956-01-01 00:00:00', "%Y-%m-%d %H:%M:%S"), 'Alert': datetime.strptime('1956-01-01 00:00:00', "%Y-%m-%d %H:%M:%S")} #1956-01-01 should be before any GLE to replay
      fillerData = np.nan
      monthRowSkip = 1 #always skip header row of monthly minute file TODO handle previous month if starting on day 1
      prevRows = 0 
      if startdt.day >= 1:
         monthRowSkip = (10+(24*(startdt.day-1)))*60+1 # skip 10 hours of previous day and header row
         prevRows = 14*60 #14 hours from prev day
      replayRows = prevRows + (24*60) #replay 24 hours and previous day rows included TODO handle last day
      # for i in range(N-1):
      for i in range(N):
         try:
            # print("reading archive file {0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt".format(Archivepath, nmdbtag[i], startdt.year, startdt.month)) #DEBUG
            # new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, nmdbtag[i], startdt.year, startdt.month), date_format= '%Y-%m-%d%H:%M:S', parse_dates=[[1,2]], names=['Time', '{0:s}'.format(nmdbtag[i]),  '{0:s}_P'.format(nmdbtag[i]), 'DELETEuncorr'], skiprows=(10+(24*(startdt.day-1)))*60+1, nrows=38*60, sep='\s+')
            # new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, nmdbtag[i], startdt.year, startdt.month), parse_dates=[0], date_format='%Y-%m-%d%', names=['Date', 'TimeOnly', '{0:s}'.format(nmdbtag[i]),  '{0:s}_P'.format(nmdbtag[i]), 'DELETEuncorr'], skiprows=(10+(24*(startdt.day-1)))*60+1, nrows=38*60, sep='\s+')
            new_archive_data = pd.read_csv('{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt'.format(Archivepath, nmdbtag[i], startdt.year, startdt.month), names=['Date', 'Time', '{0:s}'.format(nmdbtag[i]),  '{0:s}_P'.format(nmdbtag[i]), 'DELETEuncorr'], skiprows=monthRowSkip, nrows=replayRows, sep='\s+')
            print(new_archive_data)  #DEBUG
            if len(new_archive_data) < replayRows:
               print('Archive data for {0:s} not long enough for replay').format(Labels[i])
               raise ValueError

         except Exception as err:
            print('Exception {0} occured. {1:s} will be excluded from alert and filler data <{2}> will be used'.format(type(err), Labels[i], fillerData))
            InAlert[i]=0
            if i==0: 
               archive_data = pd.DataFrame({ 'Time': pd.date_range(start=start, end="{0:s} 23:59".format(replayStart.strftime("%Y-%m-%d")),freq='1min')}) 
               archive_data.index = archive_data['Time']
               archive_data=archive_data.drop(columns=['Time'])
               print(archive_data)  #DEBUG
            archive_data['{0:s}'.format(nmdbtag[i])]=fillerData
            archive_data['{0:s}_P'.format(nmdbtag[i])]=fillerData
         else:
            # new_archive_data.append(pd.read_csv("{0:s}NMDB/{1:s}/{1:s}_{2:d}_{3:02.0f}_1min_NMDB.txt".format(Archivepath, nmdbtag[i], startdt.year, startdt.month), names=["Date", "Time", "{0:s}".format(nmdbtag[i]),  "{0:s}_P".format(nmdbtag[i]), "DELETEuncorr"], skiprows=(10+(24*(startdt.day-1)))*60+1, nrows=38*60, sep='\s+'))
            new_archive_data['Time'] = new_archive_data.apply(lambda r: pd.Timestamp.combine(datetime.strptime(r['Date'], '%Y-%m-%d').date(), datetime.strptime(r['Time'], '%H:%M:%S').time()), axis=1)
            # print(new_archive_data)  #DEBUG
            
            # new_archive_data=new_archive_data.drop(columns=['Date'])
            new_archive_data.index = new_archive_data['Time']
            # print(new_archive_data.loc[start])  #DEBUG
            new_archive_data=new_archive_data.drop(columns=['DELETEuncorr'])
            new_archive_data=new_archive_data.drop(columns=['Date'])
            new_archive_data=new_archive_data.drop(columns=['Time'])
            # print(new_archive_data.info(verbose=True, show_counts=True))  #DEBUG
            if i==0: 
               archive_data = new_archive_data
               #print(archive_data)  #DEBUG

            else: 
               # new_archive_data=new_archive_data.drop(columns=['Time'])
               archive_data = archive_data.join(new_archive_data, how='left')
               # print(archive_data)  #DEBUG
            # print(archive_data.loc[0])  #DEBUG



            """raw_data[-1]['Time'] =pd.to_datetime(raw_data[-1]['Time'],infer_datetime_format=True)  
            raw_data[-1]['Time'] = raw_data[-1]['Time'].dt.tz_localize(None)
            raw_data[-1].index = raw_data[-1]['Time']
            raw_data[-1]=raw_data[-1].drop(columns=['Time'])
            raw_data[-1].to_csv('{0:s}/GLE_Alarm_{1:s}.txt'.format(Outpath,nm[i]), sep=',',date_format='%y/%m/%d %H:%M:%S') """

      # print(archive_data.isna().sum())  #DEBUG
      archive_data = archive_data.mask(0.0==archive_data) #Make 0.0 values NaN
      # print(archive_data.isna().sum())  #DEBUG
      # sys.exit()  #DEBUG

      # print(archive_data)  #DEBUG
      raw_data = archive_data[:(prevRows+1)]
      archive_data = archive_data[(prevRows+1):]
      
      # print(raw_data)  #DEBUG
      # print(archive_data)  #DEBUG
      # print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG
      
      # df = Fulldf.join(raw_data, how='left')
      print(raw_data.info(verbose=True, show_counts=True))  #DEBUG
      print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
      


   else:
      ########################
      ### Merge information from ql 
      ########################
      # raw_data=[]

      for i in range(N-1):
         raw_data.append(pd.read_json(Inpath+'/'+nm[i]+'_ql_l'+str(Ndays)+'d_1min.json'))
         raw_data[-1]['Time'] =pd.to_datetime(raw_data[-1]['Time'],infer_datetime_format=True)  
         raw_data[-1]['Time'] = raw_data[-1]['Time'].dt.tz_localize(None)
         raw_data[-1].index = raw_data[-1]['Time']
         raw_data[-1]=raw_data[-1].drop(columns=['Time'])
         raw_data[-1].to_csv('{0:s}/GLE_Alarm_{1:s}.txt'.format(Outpath,nm[i]), sep=',',date_format='%y/%m/%d %H:%M:%S')

   
   # print(Fulldf.info(verbose=True, show_counts=True))  #DEBUG
   print(raw_data.info(verbose=True, show_counts=True))  #DEBUG

   df = Fulldf.join(raw_data, how='left')
   #df.to_csv('{0:s}/GLE_Alarm.txt'.format(Outpath), sep=',',date_format='%y/%m/%d %H:%M:%S')

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

   while(True): #will break when out of archive_data but will always run once


      for i in range(N):
         df[nmdbtag[i]+'T']=df[nmdbtag[i]].rolling(str(T)+'min',min_periods=T).mean()
         df[nmdbtag[i]+'T']=df[nmdbtag[i]+'T'] *60/History[i]    #Get real count/minute (without historical normalization)
         df[nmdbtag[i]+'T0']=df[nmdbtag[i]].rolling(str(T0)+'min',min_periods=T0-1).mean()
         df[nmdbtag[i]+'Tb0']=df[nmdbtag[i]].rolling(str(Tb+T0)+'min',min_periods=Tb).mean()
         df[nmdbtag[i]+'Tb']=((Tb+T0)*df[nmdbtag[i]+'Tb0']-T0*df[nmdbtag[i]+'T0'])/Tb  * 60/History[i]
         df[nmdbtag[i]+'Ith']=df[nmdbtag[i]+'T']/df[nmdbtag[i]+'Tb']
         df[nmdbtag[i]+'F'] = np.where(df[nmdbtag[i]+'Ith']< 1.+Level/100., 0., 1)
         df[nmdbtag[i]+'F'] = np.where(np.isnan(df[nmdbtag[i]+'Ith']), 0.,  df[nmdbtag[i]+'F'])
      
      for i in range(N):
         #df=df.drop(columns=[nmdbtag[i]])
         df=df.drop(columns=[nmdbtag[i]+'T0'])
         df=df.drop(columns=[nmdbtag[i]+'Tb0'])
         df=df.drop(columns=[nmdbtag[i]+'Tb'])

      ########################
      #CALULATE THE NUMBER OF STATIONS ABOVE THE LEVEL
      ########################

      Nabove=np.zeros(len(df))
      for i in range(N):
         if InAlert[i]==1:
            Nabove+=df[nmdbtag[i]+'F']
      df['Nabove']=Nabove

      ########################
      #Define Status
      ########################
      #0: Quiet
      #1: Watch
      #2: Warning
      #>=3: Alert

      Status=['Quiet','Watch','Warning','Alert']
      Statuscol=['gray','blue','orange','red']
      df['Status'] = np.where(df['Nabove']==0, 0.,df['Nabove'])
      df['Status'] = np.where(df['Nabove']>=3, 3.,df['Status'])

      #print(df)  #DEBUG
      #print(df.info(verbose=True, show_counts=True))  #DEBUG


      ########################
      ### SEND EMAIL IF NEEDED
      ########################
      
      if (not isReplay):
         #Load time when the last alarm emails were sent
         with open(Inpath+'/'+'lastemails.json') as lastemailsjson:
            lastemails = json.load(lastemailsjson)
         #Format time to timestamp
         for i in range(3):
               lastemails[Status[i+1]] =pd.to_datetime(lastemails[Status[i+1]],infer_datetime_format=True)  
      # print(lastemails)  #DEBUG
      #Sender
      # sender = 'mangeard@spacewx.bartol.udel.edu'
      sender = 'sender@example.com' #DEBUG
      #Header
      #header= """From: mangeard@udel.edu\nTo: mangeard@udel.edu\n"""
      #header= """From: Pierre-Simon Mangeard  <mangeard@udel.edu>\nTo: Pierre-Simon Mangeard <mangeard@udel.edu>\n"""
      # header= """From: GLE Alarm  <glealarm-noreply@udel.edu>\nTo: Pierre-Simon Mangeard <mangeard@udel.edu>\n"""
      header= """From: GLE Alarm  <noreply@example.com>\nTo: Pierre-Simon Mangeard <sender@example.com>\n"""  #DEBUG

      # Bcc= """Bcc: psmangeard@gmail.com \n"""
      Bcc= """Bcc: sender@example.com \n"""
      #Text files containing the email lists
      # fmail=[Inpath+"/mail_to_watch.txt",Inpath+"/mail_to_wning.txt",Inpath+"/mail_to_alert.txt"]
      fmail=[Inpath+"/mail_to_watch_fake.txt",Inpath+"/mail_to_wning_fake.txt",Inpath+"/mail_to_alert_fake.txt"] #DEBUG
      
      #For Test purposes
      #fmail=[Inpath+"/mail_to_watch_test.txt",Inpath+"/mail_to_wning_test.txt",Inpath+"/mail_to_alert_test.txt"]

      #Default receiver
      # Thereceivers=['mangeard@udel.edu']
      Thereceivers=['default@example.com'] #DEBUG

      # print(df[-10:])

      #Last considered minute:
      LastStatus= df.iloc[-1].Status
      if LastStatus != 0:          #  the alarm level is not Quiet: Need to check previous minutes
         #Look for the starting minute of the alarm level
         i=1
         while df.iloc[-1-i].Status == LastStatus:
            i=i+1

         #Index J="-1-i" is the index of the last minute prior the current alarm level
         J=-1-i
         #Index J+1 is the first minute of the current alarm level      
         if df.iloc[J+1].Status > df.iloc[J].Status:  #Check if an email has already been sent else don't send any
            #print("The start of the alarm level is a rise of alarm level. Checking if an email has already been sent")
            if df.iloc[J+1].Time > lastemails[Status[int(LastStatus)]]: #Email has not been sent yet
               #print(df.iloc[J].Status,df.iloc[J].Time)
               #print(df.iloc[J+1].Status,df.iloc[J+1].Time)
               #print(df.iloc[-1].Status,df.iloc[-1].Time)
               #print("Email has not been sent yet! Let's send it!")
               ###########################################################
               ###########################################################
               ###########################################################
               ###SEND EMAIL
               ###########################################################
               ###########################################################
               ###########################################################            
               # print(df.info(verbose=True, show_counts=True))  #DEBUG
               # print("email starting")  #DEBUG
      
               # sys.exit() #DEBUG

               msg = EmailMessage()
               
               #Receivers: Add the mailing list corresponding to the alarm level
               Add_Emailreceivers(fmail[int(int(LastStatus))-1],Thereceivers)
               #subject: Simple and depend on the alarm level
               subject ="""Subject: gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[int(LastStatus)],df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"))
               subject2 ="""gle alarm ({0:s}) at {1:s} (UT)\n""".format(Status[int(LastStatus)],df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"))

               #subject ="""gle alarm ({0:s})""".format(Status[int(LastStatus)])

               #print(subject)

               #Body of the message
               #It depends of the alarm status and should include time, and stations above threshold
               #and the link to access the webpage with the plot
               body= "{0:s} (UT): {1:s} alarm\n".format(df.iloc[-1].Time.strftime("%Y-%m-%d %H:%M:%S"),Status[int(LastStatus)])
               body=body+"Rate increase(s):\n"
               for i in range(N):
                  if InAlert[i]==1 and df.iloc[J+1][nmdbtag[i]+'F'] ==1:
                     body=body+"{0:s} ({1:s}): {2:s} (UT), {3:4.2f}%\n".format(Labels[i],nmdbtag[i],df.iloc[J+1].Time.strftime("%Y-%m-%d %H:%M:%S"),100.*(df.iloc[J+1][nmdbtag[i]+'Ith']-1.))
               body=body+"{0:s}\n".format(urlalarm)  
               
               print(Thereceivers)
            
               #Make message
               message=header+Bcc+subject+body 
               #message=subject+body
               print(body)
               msg.set_content(body)
               # msg['From'] = 'GLE Alarm System <mangeard@udel.edu>'
               msg['From'] = 'GLE Alarm System <gle@example.com>' #DEBUG
               #msg['From'] = 'Pierre-Simon Mangeard <mangeard@udel.edu>'
   
               msg['To'] = Thereceivers[0]
               #msg['Bcc'] = 'mangeard@udel.edu,pierresimonmangeard@yahoo.fr,abydosp@yahoo.fr,psmangeard@gmail.com'
               msg['Bcc'] = ', '.join(Thereceivers[1:])  
               
               msg['Subject'] = subject2

               print(msg) 
               
               #Send the email
               print("Let's send an email")
               #print(message)
               df.iloc[-360:].to_csv('{0:s}/GLE_{1:s}_{2:s}.txt'.format(
                        Outpath,Status[int(LastStatus)],df.iloc[-1].Time.strftime("%Y%m%d_%H%M%S")),
                        sep=',',date_format='%y/%m/%d %H:%M:%S')


               # sys.exit() #DEBUG

               #smtpObj2 = smtplib.SMTP('localhost') 
               """             
               #DEBUG
               smtpObj2 = smtplib.SMTP('mail.udel.edu')
               smtpObj2.send_message(msg)
               smtpObj2.quit()

               """
               #try:
               #   smtpObj = smtplib.SMTP('localhost')
               #   smtpObj.sendmail(sender, Thereceivers, message)         
               #   print ("Successfully sent email")
               #except:
               #    print ("Error: unable to send email")


               #SendEmail(senders,Thereceivers,message)

               ###########################################################
               #print("Let's update the file containing the time of the last emails!")
               lastemails[Status[int(LastStatus)]]=df.iloc[J+1].Time
               #print("New time of last email:",lastemails[Status[int(LastStatus)]])

               # print(lastemails) #DEBUG
               # sys.exit() #DEBUG

      if (not isReplay):
         #Format timestamp to time
         for i in range(3):
               lastemails[Status[i+1]] =lastemails[Status[i+1]].strftime("%Y-%m-%d %H:%M:%S")  
         #Save time when the last alarm emails were sent
         #print(lastemails)
         with open(Inpath+'/'+'lastemails.json','w') as lastemailsjson:
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

      fig.savefig('{0:s}/GLE_Alarm.png'.format(Outpath))

      
      #for i in range(N-1):
      #   df=df.drop(columns=[nmdbtag[i+1]+'T'])
      #   df=df.drop(columns=[nmdbtag[i+1]+'Ith'])
      #   df=df.drop(columns=[nmdbtag[i+1]])

      #print(df.iloc[-10:])
      #print("--- %s seconds ---" % (time.time() - start_exetime))
      
      plt.show()

      if 0==len(archive_data) : 
         print("NO ARCHIVE DATA LEFT") #DEBUG
         print(df.info(verbose=True, show_counts=True))  #DEBUG
         if dailyDump:
            df.to_csv('{0:s}/GLE_Day_{1:s}.txt'.format(
                        Outpath,df.iloc[-1].Time.strftime("%Y%m%d")),
                        sep=',',date_format='%y/%m/%d %H:%M:%S')
         break #ends the while loop
      
     
      now+=timedelta(minutes=1)
      print("now =", now) #DEBUG
      end = now.strftime("%Y-%m-%d %H:%M")

      startdt = now - timedelta(hours=14)
      start= startdt.strftime("%Y-%m-%d %H:%M")
      #print(df[-2:])  #DEBUG
      #print(archive_data[:end])  #DEBUG
      df=pd.concat([df, archive_data[:end]])
      df['Time'][-1]=end

      archive_data=archive_data[1:]

      # print(df.info(verbose=True, show_counts=True))  #DEBUG
      #print(df[-2:])  #DEBUG
      # print(archive_data.info(verbose=True, show_counts=True))  #DEBUG
      
      # sys.exit() #DEBUG


if __name__ == "__main__":
   main(sys.argv[1:])



#END
