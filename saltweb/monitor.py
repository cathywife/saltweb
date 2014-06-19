#!/usr/bin/env python
#coding=utf-8
#author: hhr
#salt-master、salt-minion宕机邮件报警
#添加新minion或删除minion自动更新数据库

import salt
import sys, time ,os
import comm, db_connector
from django.core.mail import send_mail
from saltweb.models import *

if not Mastermonitor.objects.filter(id=1):
    Mastermonitor.objects.create(ip='%s' % comm.masterip)
code = os.system("/etc/init.d/salt-master status >/dev/null")
if code != 0:
    status = 'down'
    Mastermonitor.objects.filter(id=1).update(status=status)
    nowtime = time.strftime("%Y-%m-%d %X")
    lasttime = Mastermonitor.objects.filter(id=1)[0].lasttime
    if not lasttime or int(time.mktime(time.strptime(nowtime, '%Y-%m-%d %X'))) > int(time.mktime(time.strptime(lasttime, '%Y-%m-%d %X'))) + comm.interval:
        Mastermonitor.objects.filter(id=1).update(nowtime=nowtime,lasttime=nowtime)
        send_mail(u'CRITICAL: salt-master down',u'saltwebmaster',comm.from_mail,comm.samail_list)
        Alarm.objects.create(hostid="saltwebmaster",msg='CRITICAL: salt-master down',to=comm.samail_list)
    sys.exit()
else:
    status = 'up'
    Mastermonitor.objects.filter(id=1).update(status=status)
c = salt.client.LocalClient()
rets = c.cmd('*','test.ping')
#try:
#    rets = c.cmd('*','test.ping')
#    Mastermonitor.objects.filter(id=1).update(status='up')
#except:
#    status = 'down'
#    nowtime = time.strftime("%Y-%m-%d %X")
#    lasttime = Mastermonitor.objects.filter(id=1)[0].lasttime
#    if not lasttime or int(time.mktime(time.strptime(nowtime, '%Y-%m-%d %X'))) > int(time.mktime(time.strptime(lasttime, '%Y-%m-%d %X'))) + comm.interval:
#        Mastermonitor.objects.filter(id=1).update(status=status,nowtime=nowtime,lasttime=nowtime)
#        send_mail(u'CRITICAL: salt-master down',u'saltwebmaster',comm.from_mail,comm.samail_list)
#        Alarm.objects.create(hostid="saltwebmaster",msg='CRITICAL: salt-master down',to=comm.samail_list)
#    sys.exit()
saltids = [r['saltid'] for r in Hosts.objects.values('saltid')]
saltkeys = c.run_job('*','cmd.run',['echo'])['minions']
newlist = list(set(rets.keys()).difference(set(saltids)))   #新增minion列表
oldlist = list(set(saltids).difference(set(saltkeys)))  #删除minion列表
downlist = list(set(saltids).difference(set(rets.keys())))  #宕机列表
for saltid in oldlist:
    Hosts.objects.filter(saltid=saltid).delete()
    Monitor.objects.filter(saltid=saltid).delete()
for saltid in newlist:
    grains = c.cmd(saltid, 'grains.items')
    os = grains[saltid]['osfullname']+grains[saltid]['osrelease']
    cpu = grains[saltid]['cpu_model']
    hostname = grains[saltid]['nodename']
    mem = grains[saltid]['mem_total']
    cpunum = int(grains[saltid]['num_cpus'])
    ip = [i for i in grains[saltid]['ipv4'] if i.startswith(comm.network_list)][0]
    Hosts.objects.create(saltid=saltid,cpu=cpu,cpunum=cpunum,mem=mem,hostname=hostname,os=os,ip=ip)
    minions = [row['saltid'] for row in Hosts.objects.values('saltid')]
    vmrets = c.cmd(saltid,'cmd.run',['ls /dev/*vda'],timeout=5) 
    if 'No such file or directory' in vmrets[saltid]:
        modelcmd = "dmidecode | grep 'Product Name: '|head -1|awk -F\: '{print $2}'|awk '{print $1,$2,$3}'"
        modelret = c.cmd(saltid,'cmd.run',[modelcmd],timeout=5)
        sncmd = "dmidecode -s system-serial-number"
        snret = c.cmd(saltid,'cmd.run',[sncmd],timeout=5)
        diskcmd = "fdisk -l 2>/dev/null|egrep '^Disk /dev/'|awk '{print $3,$4}'"
        diskret = c.cmd(saltid,'cmd.run',[diskcmd],timeout=5)
        nowtime = time.strftime("%Y-%m-%d %H:%M:%S")
        Hosts.objects.filter(saltid=saltid).update(model=modelret[saltid],
        sn=snret[saltid],disk=diskret[saltid],host_type='实体机',nowtime=nowtime)
for down in downlist:
    rets[down] =  'False'
if oldlist:
    saltids = [r['saltid'] for r in Hosts.objects.values('saltid')] #如果删除minion则重新生成
    rets = c.cmd('*','test.ping')
for saltid,saltstatus in rets.items():
    ip = Hosts.objects.get(saltid=saltid).ip
    if saltid in saltids:
        num = 0
        nowtime = time.strftime("%Y-%m-%d %X")
        if not Monitor.objects.filter(saltid=saltid):
            Monitor.objects.create(saltid=saltid,ip=ip,saltstatus=str(saltstatus),nowtime=nowtime)
        if str(saltstatus) == 'False':
            num = Monitor.objects.filter(saltid=saltid)[0].num
            num +=1
            lasttime = Monitor.objects.filter(saltid=saltid)[0].lasttime
            if not lasttime and num >3:
                num = 0
                sendmail = 1
                lasttime = time.strftime("%Y-%m-%d %X")
                Monitor.objects.filter(saltid=saltid).update(saltstatus=str(saltstatus),num=num,nowtime=nowtime,lasttime=lasttime,sendmail=sendmail)
            if num > 3 and int(time.mktime(time.strptime(nowtime, '%Y-%m-%d %X'))) > int(time.mktime(time.strptime(lasttime, '%Y-%m-%d %X'))) + comm.interval:
                num = 0
                sendmail = 1
                lasttime = time.strftime("%Y-%m-%d %X")
                Monitor.objects.filter(saltid=saltid).update(saltstatus=str(saltstatus),num=num,nowtime=nowtime,lasttime=lasttime,sendmail=sendmail)
            Monitor.objects.filter(saltid=saltid).update(saltstatus=str(saltstatus),num=num,nowtime=nowtime)
        else:
            Monitor.objects.filter(saltid=saltid).update(saltstatus=str(saltstatus),num=num,nowtime=nowtime)
downhostlist = [i.saltid for i in Monitor.objects.filter(sendmail=1,closemail=0)]
if downhostlist:
    Monitor.objects.all().update(sendmail=0)
    msg = u'CRITICAL: host saltstatus down'
    send_mail(msg,str(downhostlist),comm.from_mail,comm.samail_list)
    Alarm.objects.create(hostid=str(downhostlist),msg=msg,to=comm.samail_list)
    users = [row['username'] for row in User.objects.values('username')]
    for user in users:
        Msg.objects.create(msgfrom='systemmonitor',msgto=user,title=msg,content=str(downhostlist))
