import datetime
import gobject
import gtk
import lockhash
import os
import platform
import re
from string import ascii_uppercase
import subprocess
import sys
import threading
import time

def findos(ui):
    if sys.platform == "linux" or sys.platform == "linux2":
        print sys.platform
        ui.ostype = 1
        ui.prefix = "sudo "
        ui.cmd = 'python /usr/local/bin/Lock.py'
        print ("ui.cmd = ", ui.cmd)
    elif sys.platform == "darwin":
        print sys.platform
        ui.ostype = 2
        ui.prefix = "sudo "
        ui.cmd = 'python /usr/local/bin/Lock.py'
    elif sys.platform == "win32":
        print sys.platform
        ui.ostype = 0
        ui.prefix = ""
        ui.cmd = 'python Lock.py'
    
def finddev(ui):
    txt = os.popen(ui.prefix + 'sedutil-cli --scan n').read()
    print "scan result : "
    print txt
 
    names = ['PhysicalDrive[0-9]', '/dev/sd[a-z]', '/dev/nvme[0-9]',  '/dev/disk[0-9]']
    idx = 0
    ui.devs_list = []
    ui.locked_list = []
    ui.setup_list = []
    ui.unlocked_list = []
    ui.nonsetup_list = []
    ui.tcg_list = []
    for index in range(len(names)): #index=0(window) 1(Linux) 2(OSX)
        print ("index= ", index)
        print names[index]
    
        m = re.search(names[index] + ".*", txt) # 1st search identify OS type and the pattern we are looking for
        
        if m:
            if (index == 0 ):
               ui.prefix = ""
            else:
               ui.prefix = "sudo "
            
            txt11 = names[index] + " .[A-z0-9]+ *[A-z0-9].*"
            
            print("looking for Opal device ", txt11)

            m = re.findall(txt11, txt) # 1 or 2 follow by anything ; look for Opal drive
            print ("m = ", m)
            if m:
                for tt in m:
                    print tt
                    m2 = re.match(names[index],tt)
                    x_words = tt.split() 
                    if (index == 0) : 
                        ui.devname = "\\\\.\\" + m2.group()
                    else:
                        ui.devname =  m2.group()
                    ui.devs_list.append(ui.devname)
                    if len(x_words) > 3 : # concatenate all word together
                        print "x_words len > 3"
                        for y in range(3,(len)(x_words)):###for y in range(3,(len)(x_words):
                            x_words[2] = x_words[2] + " " + x_words[y]
                    y_words = x_words[2].split(":",1)
                    print ("y_words = ", y_words)
                    print ("y_words[0] = ", y_words[0])
                    print ("y_words[1] = ", y_words[1])
                    ui.vendor_list.append(y_words[0])
                    y = y_words[1].replace(" ", "")
                    y_words[1] = y 
                    ui.series_list.append(y_words[1]) 
                    
                    if x_words[1] == "No":
                        ui.opal_ver_list.append("None")
                    else:
                        if x_words[1] == "1" or x_words[1] == "2":
                            ui.opal_ver_list.append("Opal " + x_words[1] + ".0")
                        elif x_words[1] == "12":
                            ui.opal_ver_list.append("Opal 1.0/2.0")
                        elif x_words[1] == "E":
                            ui.opal_ver_list.append("Enterprise")
                        elif x_words[1] == "L":
                            ui.opal_ver_list.append("Opallite")
                        elif x_words[1] == "P":
                            ui.opal_ver_list.append("Pyrrite")
                        else:
                            ui.opal_ver_list.append(x_words[1])
        else:
            print "No Matched : ", names[index]
    if ui.devs_list != []:
        for i in range(len(ui.devs_list)):
            queryText = os.popen(ui.prefix + 'sedutil-cli --query ' + ui.devs_list[i]).read()
            
            txt_msid = os.popen(ui.prefix + "sedutil-cli --printDefaultPassword " + ui.devs_list[i] ).read()
            msid = 'N/A'
            if txt_msid != '' :
                x_words = txt_msid.split(': ',1)
                msid = re.sub(r'\n', '', x_words[1])
            
            regex = ':\s*[A-z0-9]+\s+([A-z0-9]+)'
            p = re.compile(regex)
            m = p.search(queryText)
            if m:
                ui.sn_list.append(m.group(1))
            else:
                ui.sn_list.append("N/A")
            ui.msid_list.append(msid)
            
            txt_TCG = "Locked = "
            txt_L = "Locked = Y"
            txt_S = "LockingEnabled = Y"
            txt_ALO = "AUTHORITY_LOCKED_OUT"
            txt_NA = "NOT_AUTHORIZED"
            #msidText = os.popen(ui.prefix + 'sedutil-cli -n --getmbrsize ' + msid + ' ' + ui.devs_list[i]).read()
            isTCG = re.search(txt_TCG, queryText)
            isLocked = re.search(txt_L, queryText)
            isSetup = (re.search(txt_S, queryText) != None) #& (msidText == '')
            if isTCG:
                if isLocked:
                    ui.locked_list.append(i)
                    ui.setup_list.append(i)
                    ui.tcg_list.append(i)
                elif isSetup:
                    ui.setup_list.append(i)
                    ui.unlocked_list.append(i)
                    ui.nonsetup_list.append(i)
                    ui.tcg_list.append(i)
                else:
                    ui.nonsetup_list.append(i)
                    ui.tcg_list.append(i)
        print ("devs_list: ",  ui.devs_list)
        print ("vendor_list: ", ui.vendor_list)
        print ("opal_ver_list: ", ui.opal_ver_list)
        print ("sn_list: ", ui.sn_list)	

def run_setupFull(button, ui, mode):
    index = ui.dev_select.get_active()
    ui.devname = ui.devs_list[ui.nonsetup_list[index]]
    dev_msid = ui.msid_list[ui.nonsetup_list[index]]
    print("lock physical device "+ ui.devname)
    pw = ui.new_pass_entry.get_text()
    pw_confirm = ui.confirm_pass_entry.get_text()
    pw_trim = re.sub('\s', '', pw)
    print pw_trim
    pw_trim_confirm = re.sub(r'\s+', '', pw_confirm)
    if len(pw_trim) < 8:# and not (digit_error or uppercase_error or lowercase_error):
        ui.msg_err("This password is too short.  Please enter a password at least 8 characters long excluding whitespace.")
    elif ui.bad_pw.has_key(pw_trim):
        ui.msg_err("This password is on the blacklist of bad passwords, please enter a stronger password.")
    elif pw_trim != pw_trim_confirm:
        ui.msg_err("The entered passwords do not match.")
    else:
        message1 = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
        message1.set_markup("Warning: If you lose your password, all data will be lost. Do you want to proceed?")
        res1 = message1.run()
        if res1 == gtk.RESPONSE_OK:
            message2 = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
            message2.set_markup("Final Warning: If you lose your password, all data will be lost. Are you sure you want to proceed?")
            res2 = message2.run()
            if res2 == gtk.RESPONSE_OK:
                message2.destroy()
                message1.destroy()
                password = lockhash.hash_pass(ui.new_pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
                ui.start_spin()
                ui.wait_instr.show()
                
                def t1_run():
                    queryText = os.popen(ui.prefix + 'sedutil-cli --query ' + ui.devname).read()
                    txt_LE = "LockingEnabled = N"
                    txt_ME = "MBREnabled = N"
                    unlocked = re.search(txt_LE, queryText)
                    activated = re.search(txt_ME, queryText)
                    status1 = -1
                    if unlocked:
                        status1 =  os.system(ui.prefix + "sedutil-cli -n --initialSetup " + password + " " + ui.devname )
                    
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW3 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 01" + timeStr + " " + password + " " + ui.devname)
                    
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 10" + timeStr + " " + password + " " + ui.devname)
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 11" + timeStr + " " + password + " " + ui.devname)
                    elif activated:
                        #dev_msid = ui.get_msid()
                        s1 = os.system(ui.prefix + "sedutil-cli -n --setSIDPassword " + dev_msid + " " + password + " " + ui.devname)
                        s2 = os.system(ui.prefix + "sedutil-cli -n --setAdmin1Pwd " + dev_msid + " " + password + " " + ui.devname)
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 10" + timeStr + " " + password + " " + ui.devname)
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 11" + timeStr + " " + password + " " + ui.devname)
                        status1 = (s1 | s2)
                
                    status2 =  os.system(ui.prefix + "sedutil-cli -n --enableLockingRange " + ui.LKRNG + " " + password + " " + ui.devname )
                    status3 =  os.system(ui.prefix + "sedutil-cli -n --setMBRdone on " + password + " " + ui.devname )
                    
                    gobject.idle_add(cleanup, status1 | status2 | status3)
                
                def cleanup(status):
                    ui.stop_spin()
                    t1.join()
                    if status !=0 :
                        ui.msg_err("Error: Setup of " + ui.devname + " failed. Try again.")
                        ui.op_instr.show()
                        ui.box_newpass.show()
                        ui.box_newpass_confirm.show()
                        ui.check_box_pass.show()
                        ui.setup_next.show()
                        ui.go_button_cancel.show()
                    else : 
                        if ui.pass_sav.get_active():
                            passSaveUSB(ui)
                        if mode == 1:
                            status5 =  os.system(ui.prefix + "sedutil-cli -n --enableLockingRange " + ui.LKRNG + " " + password + " " + ui.devname )
                            status6 =  os.system(ui.prefix + "sedutil-cli -n --setLockingrange " + ui.LKRNG + " LK " + password + " " + ui.devname )
                            status7 =  os.system(ui.prefix + "sedutil-cli -n --setMBRDone on " + password + " " + ui.devname )
                        ui.query(1)
                        ui.msg_ok("Password for " + ui.devname + " set up successfully.")
                        if mode == 0:
                            ui.setup_prompt2()
                        else:
                            ui.updateDevs(index,[1,2])
                            ui.returnToMain()
                            
                t1 = threading.Thread(target=t1_run, args=())
                t1.start()
                start_time = time.time()
                t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
                t2.start()

def run_pbaWrite(button, ui, mode):
    print "pba_write"
    status = -1
    password = ""
    index = ui.dev_select.get_active()
    if mode == 0: #update, add usb check
        ui.devname = ui.devs_list[ui.setup_list[index]]
        if ui.check_pass_rd.get_active():
            password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
        else:
            password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    else:
        ui.devname = ui.devs_list[ui.nonsetup_list[index]]
        password = lockhash.hash_pass(ui.new_pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    ui.start_spin()
    ui.pba_wait_instr.show()
    
    def t1_run():
        if password != None:
            status = os.system( ui.prefix + "sedutil-cli -n --loadpbaimage " + password + " n " + ui.devname )
            gobject.idle_add(cleanup, status)
        else:
            gobject.idle_add(cleanup, 1)
        
        
    def cleanup(status):
        ui.stop_spin()
        t1.join()
        if status != 0 :
            ui.msg_err("Error: Writing PBA image to " + ui.devname + " failed.")
            
            ui.op_instr.show()
            if mode == 1:
                ui.setupLockOnly.show()
                ui.setupLockPBA.show()
            else:
                ui.box_pass.show()
                ui.check_box_pass.show()
                ui.updatePBA_button.show()
                ui.go_button_cancel.show()
        else :
            status2 =  os.system(ui.prefix + "sedutil-cli -n --setMBREnable on " + password + " " + ui.devname )
            p = subprocess.check_output([ui.prefix + "sedutil-cli", "-n", "--pbaValid", devpass, ui.devname])
            pba_regex = 'PBA image version: (.+)\nPBA image valid'
            m1 = re.match(pba_regex, p1)
            pba_ver = m1.group(1)
            ui.msg_ok("PBA image " + pba_ver + " written to " + ui.devname + " successfully.")
            if mode == 0:
                ui.setup_finish()
            else:
                ui.returnToMain()
    
    t1 = threading.Thread(target=t1_run, args=())
    t1.start()
    start_time = time.time()
    t2 = threading.Thread(target=timeout_track, args=(ui, 300.0, start_time, t1))
    t2.start()

def run_changePW(button, ui):
    #retrieve old, new, and confirm new password texts
    old_hash = ""
    if ui.check_pass_rd.get_active():
        old_hash = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
        if old_hash == None or old_hash == 'x':
            return
    else:
        old_pass = ui.pass_entry.get_text()
        old_trim = re.sub('\s', '', old_pass)
        old_hash = lockhash.hash_pass(old_trim, ui.dev_sn.get_text(), ui.dev_msid.get_text())
    new_pass = ui.new_pass_entry.get_text()
    new_pass_confirm = ui.confirm_pass_entry.get_text()
    
    pw_trim = re.sub('\s', '', new_pass)
    pw_trim_confirm = re.sub(r'\s+', '', new_pass_confirm)
    if len(pw_trim) < 8:
        ui.msg_err("The new password is too short.  Please enter a password at least 8 characters long excluding whitespace.")
    elif ui.bad_pw.has_key(pw_trim):
        ui.msg_err("The new password is on the blacklist of bad passwords, please enter a stronger password.")
    elif pw_trim != pw_trim_confirm:
        ui.msg_err("The new entered passwords do not match.")
    else:
        index = ui.dev_select.get_active()
        ui.devname = ui.devs_list[ui.setup_list[index]]
        new_hash = lockhash.hash_pass(ui.new_pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
        ui.start_spin()
        ui.wait_instr.show()
        
        def t1_run():
            txt1 = "NOT_AUTHORIZED"
            txt2 = "AUTHORITY_LOCKED_OUT"
            p1 = subprocess.check_output([ui.prefix + "sedutil-cli", "-n", "--setSIDPassword", old_hash, new_hash, ui.devname])
            na1 = re.search(txt1, p1)
            alo1 = re.search(txt2, p1)
            p2 = subprocess.check_output([ui.prefix + "sedutil-cli", "-n", "--setAdmin1Pwd", old_hash, new_hash, ui.devname])
            na2 = re.search(txt1, p2)
            alo2 = re.search(txt2, p2)
            gobject.idle_add(cleanup, alo1 or alo2, na1 or na2)
            
        def cleanup(alo, na):
            if alo:
                ui.msg_err("Error: You have been locked out of " + ui.devname + " due to multiple failed authentication attempts.  Please reboot and try again.")
            elif na:
                ui.msg_err("Error: Incorrect password, please try again.")
            else :
                if ui.pass_sav.get_active():
                    passSaveUSB(ui)
                t1.join()
                ui.stop_spin()
                timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                timeStr = timeStr[2:]
                statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 10" + timeStr + " " + new_hash + " " + ui.devname)
                timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                timeStr = timeStr[2:]
                statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 11" + timeStr + " " + new_hash + " " + ui.devname)
                ui.msg_ok("Password for " + ui.devname + " changed successfully.") 
                ui.returnToMain()
            
        t1 = threading.Thread(target=t1_run, args=())
        t1.start()
        start_time = time.time()
        t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
        t2.start()

def run_revertUser(button, ui):
    if ui.eraseData_check.get_active() == True:
        message = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
        message.set_markup("Warning : Revert with password erase all data. Do you want to proceed?")
        res = message.run()
        print message.get_widget_for_response(gtk.RESPONSE_OK)
        print gtk.RESPONSE_OK
        if res == gtk.RESPONSE_OK :
            print "User click OK button"
            messageA = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
            messageA.set_markup("Warning Warning Warning : Revert with password erase all data. Do you really want to proceed?")
            resA = messageA.run()

            if resA == gtk.RESPONSE_OK : 
                messageA.destroy()
                message.destroy()
                ui.start_spin()
                ui.wait_instr.show()
                password = ""
                if ui.check_pass_rd.get_active():
                    password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
                else:
                    password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
                def t1_run():
                    print "execute the revert with password"
                    
                    if password == None or password == 'x':
                        gobject.idle_add(cleanup, 0, 1)
                    else:
                        index = ui.dev_select.get_active()
                        ui.devname = ui.devs_list[ui.setup_list[index]]
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 15" + timeStr + " " + password + " " + ui.devname)
                        txt1 = "NOT_AUTHORIZED"
                        txt2 = "AUTHORITY_LOCKED_OUT"
                        p1 = subprocess.check_output([ui.prefix + "sedutil-cli", "-n", "--revertTPer", password, ui.devname])
                        na = re.search(txt1, p1)
                        alo = re.search(txt2, p1)
                        gobject.idle_add(cleanup, alo, na)
                    
                def cleanup(alo, na):
                    t1.join()
                    ui.stop_spin()
                    if na :
                        ui.msg_err("Error: Invalid password, try again.")
                    elif alo :
                        ui.msg_err("Error: Locked out due to multiple failed attempts.  Please reboot and try again.")
                    else :
                        index = ui.dev_select.get_active()
                        dev_msid = ui.msid_list[ui.setup_list[index]]
                        
                        status = os.system(ui.prefix + "sedutil-cli -n --activate " + dev_msid + " " + ui.devname)
                        
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW1 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 05" + timeStr + " " + dev_msid + " " + ui.devname)
                        
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW2 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 08" + timeStr + " " + dev_msid + " " + ui.devname)
                        
                        timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                        timeStr = timeStr[2:]
                        statusAW3 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 01" + timeStr + " " + dev_msid + " " + ui.devname)
                        ui.msg_ok("Device " + ui.devname + " successfully reverted with password.")
                        index = ui.dev_select.get_active()
                        ui.query(1)
                        ui.updateDevs(index,[4])
                        ui.returnToMain()
                t1 = threading.Thread(target=t1_run, args=())
                t1.start()
                start_time = time.time()
                t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
                t2.start()
        
    else:
        index = ui.dev_select.get_active()
        ui.devname = ui.devs_list[ui.setup_list[index]]
        ui.start_spin()
        ui.wait_instr.show()
        password = ''
        if ui.check_pass_rd.get_active():
            password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
        else:
            password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
        
        def t1_run():
            txt1 = "NOT_AUTHORIZED"
            txt2 = "AUTHORITY_LOCKED_OUT"
            
            if password == None or password == 'x':
                gobject.idle_add(cleanup, 1, 0)
            
            timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            timeStr = timeStr[2:]
            statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 13" + timeStr + " " + password + " " + ui.devname)
            p = ''
            if statusAW == 0:
                status1 =  os.system(ui.prefix + "sedutil-cli -n --setMBRdone on " + password + " " + ui.devname )
                status2 =  os.system(ui.prefix + "sedutil-cli -n --setLockingRange " + ui.LKRNG + " " 
                        + ui.LKATTR + " " + password + " " + ui.devname)
                p = subprocess.check_output([ui.prefix + "sedutil-cli", "-n", "--revertnoerase", password, ui.devname])
                na = re.search(txt1, p)
                alo = re.search(txt2, p)
                gobject.idle_add(cleanup, na, alo)
            else:
                gobject.idle_add(cleanup, 1, 0)
            
        def cleanup(na, alo):
            ui.stop_spin()
            t1.join()
            if na :
                ui.msg_err("Error: Invalid password, try again.")
                #timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                #timeStr = timeStr[2:]
                #statusAW = os.system(ui.prefix + "sedutil-cli --auditwrite 14" + timeStr + " " + dev_msid + " " + ui.devname)
            elif alo :
                ui.msg_err("Error: Locked out due to multiple failed attempts.  Please reboot and try again.")
            else :
                #query to verify that LockingEnabled = N, proceed if affirm
                p0 = subprocess.check_output([ui.prefix + "sedutil-cli", "--query", ui.devname])
                txtLE = "LockingEnabled = N"
                le_check = re.search(txtLE, p0)
                if le_check:
                    index = ui.dev_select.get_active()
                    dev_msid = ui.msid_list[ui.setup_list[index]]
                    p1 = subprocess.check_output([ui.prefix + "sedutil-cli", "-n", "--revertTPer", password, ui.devname])
                    
                    status = os.system(ui.prefix + "sedutil-cli -n --activate " + dev_msid + " " + ui.devname)
                    
                    timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    timeStr = timeStr[2:]
                    statusAW1 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 04" + timeStr + " " + dev_msid + " " + ui.devname)
                    
                    timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    timeStr = timeStr[2:]
                    statusAW2 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 01" + timeStr + " " + dev_msid + " " + ui.devname)
                    ui.msg_ok("Device " + ui.devname + " successfully reverted with password.")
                    index = ui.dev_select.get_active()
                    ui.query(1)
                    ui.updateDevs(index,[4])
                    ui.returnToMain()
                else:
                    ui.msg_err("Error: Revert failed.")
        t1 = threading.Thread(target=t1_run, args=())
        t1.start()
        start_time = time.time()
        t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
        t2.start()

def run_revertPSID(button, ui):
    message = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
    message.set_markup("Warning : Revert with PSID erase all data. Do you want to proceed?")
    res = message.run()
    print message.get_widget_for_response(gtk.RESPONSE_OK)
    print gtk.RESPONSE_OK
    if res == gtk.RESPONSE_OK :
        print "User click OK button"
        messageA = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
        messageA.set_markup("Warning Warning Warning : Revert with PSID erase all data. Do you really want to proceed?")
        resA = messageA.run()

        if resA == gtk.RESPONSE_OK :
            messageA.destroy()
            message.destroy()
            ui.start_spin()
            ui.wait_instr.show()
            index = ui.dev_select.get_active()
            
            def t1_run():            
                print "execute the revert with PSID"
                psid = ui.revert_psid_entry.get_text()
                
                ui.devname = ui.devs_list[ui.setup_list[index]]
                
                status =  os.system(ui.prefix + "sedutil-cli -n --yesIreallywanttoERASEALLmydatausingthePSID " + psid + " " + ui.devname )
                gobject.idle_add(cleanup, status)
            
            def cleanup(status):
                ui.stop_spin()
                t1.join()
                if status != 0 :
                    ui.msg_err("Error: Incorrect PSID, please try again." )
                else :
                    index = ui.dev_select.get_active()
                    dev_msid = ui.msid_list[ui.setup_list[index]]
                    status = os.system(ui.prefix + "sedutil-cli -n --activate " + dev_msid + " " + ui.devname)
                    timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    timeStr = timeStr[2:]
                    statusAW1 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 06" + timeStr + " " + dev_msid + " " + ui.devname)
                    
                    timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    timeStr = timeStr[2:]
                    statusAW = os.system(ui.prefix + "sedutil-cli -n --auditwrite 08" + timeStr + " " + dev_msid + " " + ui.devname)
                    
                    timeStr = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                    timeStr = timeStr[2:]
                    statusAW2 = os.system(ui.prefix + "sedutil-cli -n --auditwrite 01" + timeStr + " " + dev_msid + " " + ui.devname)
                    ui.msg_ok("Device " + ui.devname + " successfully reverted with PSID.")
                    index = ui.dev_select.get_active()
                    ui.query(1)
                    ui.updateDevs(index,[4])
                    ui.returnToMain()
            
            t1 = threading.Thread(target=t1_run, args=())
            t1.start()
            start_time = time.time()
            t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
            t2.start()

def run_lockset(button, ui):
    index = ui.dev_select.get_active()
    ui.devname = ui.devs_list[ui.unlocked_list[index]]
    print("Set Lock Attribute of physical device " + ui.devname)
    ui.start_spin()
    ui.wait_instr.show()
    password = ""
    if ui.check_pass_rd.get_active():
        password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
    else:
        password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    def t1_run():
        
        if password == None or password == 'x':
            gobject.idle_add(cleanup, 1)
        else:
            status1 =  os.system(ui.prefix + "sedutil-cli -n --enableLockingRange " + ui.LKRNG + " " 
                    + password + " " + ui.devname )
            status2 =  os.system(ui.prefix + "sedutil-cli -n --setLockingrange " + ui.LKRNG + " LK "
                    + password + " " + ui.devname )
            status3 =  os.system(ui.prefix + "sedutil-cli -n --setMBRDone on " + password + " " + ui.devname )
            status4 =  os.system(ui.prefix + "sedutil-cli -n --setMBREnable on " + password + " " + ui.devname )
            gobject.idle_add(cleanup, status1 | status2 | status3 | status4)
        
    def cleanup(status):
        ui.stop_spin()
        t1.join()
        if (status) != 0 :
            ui.msg_err("TCG Lock setting unsuccess")
        else :
            ui.msg_ok("TCG Lock setting success") 
            ui.query(1)
            ui.updateDevs(index,[1,2])
            ui.returnToMain()

    t1 = threading.Thread(target=t1_run, args=())
    t1.start()
    start_time = time.time()
    t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
    t2.start()

def run_unlockPBA(button, ui):
    index = ui.dev_select.get_active()
    ui.devname = ui.devs_list[ui.locked_list[index]]
    print("PreBoot Authorization physical device " + ui.devname)
    ui.LKATTR = "RW"
    password = ''
    if ui.check_pass_rd.get_active():
        password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
    else:
        password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    ui.start_spin()
    ui.wait_instr.show()
    def t1_run():
        status1 =  os.system(ui.prefix + "sedutil-cli -n --setMBRdone on " + password + " " + ui.devname )
        status2 =  os.system(ui.prefix + "sedutil-cli -n --setLockingRange " + ui.LKRNG + " " 
                + ui.LKATTR + " " + password + " " + ui.devname)
        gobject.idle_add(cleanup, status1 | status2)
    def cleanup(status):
        ui.stop_spin()
        t1.join()
        if status != 0 :
            ui.msg_err("Error: Preboot unlock of " + ui.devname + " failed.")
            ui.unlock_prompt(ui)
        else :
            ui.msg_ok(ui.devname + " preboot unlocked successfully.")
            ui.query(1)
            ui.updateDevs(index,[2,3])
            ui.returnToMain()
    t1 = threading.Thread(target=t1_run, args=())
    t1.start()
    start_time = time.time()
    t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
    t2.start()

def run_unlockFull(button, ui):
    index = ui.dev_select.get_active()
    ui.devname = ui.devs_list[ui.setup_list[index]]
    print("unlock physical device " + ui.devname)
    password = ""
    if ui.check_pass_rd.get_active():
        password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
    else:
        password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    ui.start_spin()
    ui.wait_instr.show()
    
    def t1_run():
        
        if password == None or password == 'x':
            gobject.idle_add(cleanup, 1)
        else:
            status1 =  os.system(ui.prefix + "sedutil-cli -n --disableLockingRange " + ui.LKRNG + " " + password + " " + ui.devname )
            status2 =  os.system(ui.prefix + "sedutil-cli -n --setMBREnable off " + password + " " + ui.devname )
            index = ui.dev_select.get_active()
            dev_msid = ui.msid_list[ui.setup_list[index]]
            status3 = os.system(ui.prefix + "sedutil-cli -n --setSIDPassword " + password + " " + dev_msid + " " + ui.devname)
            status4 = os.system(ui.prefix + "sedutil-cli -n --setAdmin1Pwd " + password + " " + dev_msid + " " + ui.devname)
            gobject.idle_add(cleanup, status1 | status2 | status3 | status4)
    
    def cleanup(status):
        ui.stop_spin()
        t1.join()
        if status != 0 :
            ui.msg_err("TCG Unlock unsuccess")
            ui.op_instr.show()
            ui.box_pass.show()
            ui.check_box_pass.show()
            ui.unlockFull_button.show()
            ui.go_button_cancel.show()
        else :
            ui.msg_ok("TCG Unlock success")
            ui.query(1)
            ui.updateDevs(index,[4])
            ui.returnToMain()
    t1 = threading.Thread(target=t1_run, args=())
    t1.start()
    start_time = time.time()
    t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
    t2.start()

def run_unlockPartial(button, ui):
    index = ui.dev_select.get_active()
    ui.devname = ui.devs_list[ui.setup_list[index]]
    print("unlock physical device " + ui.devname)
    password = ""
    if ui.check_pass_rd.get_active():
        password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
    else:
        password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    ui.start_spin()
    ui.wait_instr.show()
    
    def t1_run():
        if password == None or password == 'x':
            gobject.idle_add(cleanup, 1)
        else:
            status1 =  os.system(ui.prefix + "sedutil-cli -n --disableLockingRange " + ui.LKRNG + " " + password + " " + ui.devname )
            status2 =  os.system(ui.prefix + "sedutil-cli -n --setMBREnable off " + password + " " + ui.devname )
            gobject.idle_add(cleanup, status1 | status2)
    
    def cleanup(status):
        ui.stop_spin()
        t1.join()
        if status != 0 :
            ui.msg_err("Error: Partial unlock failed")
            ui.op_instr.show()
            ui.box_pass.show()
            ui.check_box_pass.show()
            ui.unlockPartial_button.show()
            ui.go_button_cancel.show()
        else :
            ui.msg_ok("Partial unlock completed")
            ui.query(1)
            if index in ui.locked_list:
                ui.updateDevs(index,[2,3])
            ui.returnToMain()
            
    t1 = threading.Thread(target=t1_run, args=())
    t1.start()
    start_time = time.time()
    t2 = threading.Thread(target=timeout_track, args=(ui, 10.0, start_time, t1))
    t2.start()

def run_unlockUSB(button, ui):
    #scan for password file directory
    folder_list = []
    dev_os = platform.system()
    if dev_os == 'Windows':
        for drive in ascii_uppercase:
            if drive != 'C' and os.path.isdir('%s:\\' % drive):
                if os.path.isdir('%s:\\FidelityLock' % drive):
                    folder_list.append(drive)
    elif dev_os == 'Linux':
        txt = os.popen(ui.prefix + 'mount -l').read()
        dev_regex = '/dev/sd[b-z][1-9]?\son\s(/[A-z/]*)\stype'
        drive_list = re.findall(dev_regex, txt)
        for d in drive_list:
            if os.path.isdir('%s/FidelityLock' % d):
                folder_list.append(d)
    if len(folder_list) == 0:
        msg_err('No password files found, check to make sure the USB is properly inserted.')
    else:
        #for each locked device, scan the folder(s) for the file
        #if file exists, read and attempt to unlock
        
        ui.start_spin()
        ui.wait_instr.show()
        def t1_run():
            dev_unlocked = []
            for i in ui.locked_list:
                pw = passReadUSB(ui, ui.vendor_list[i], ui.sn_list[i])
                if pw == None:
                   break
                elif pw != 'x':
                    #attempt to unlock
                    ui.LKATTR = "RW"
                    ui.LKRNG = "0"
                    status1 =  os.system(ui.prefix + "sedutil-cli -n --setMBRdone on " + pw + " " + ui.devs_list[i] )
                    status2 =  os.system(ui.prefix + "sedutil-cli -n --setLockingRange " + ui.LKRNG + " " 
                            + ui.LKATTR + " " + pw + " " + ui.devs_list[i])
                    if (status1 | status2) == 0 :
                        dev_unlocked.append(i)
            gobject.idle_add(cleanup, dev_unlocked)
            
        def cleanup(dev_unlocked):
            if len(dev_unlocked) == 0:
                ui.msg_err('No drives were unlocked.')
            else:
                txt = 'The following drives were unlocked: '
                for j in range(len(dev_unlocked) - 1):
                    txt = txt + ui.devs_list[dev_unlocked[j]] + ','
                txt = txt + dev_unlocked[len(dev_unlocked) - 1]
                ui.msg_ok(txt)
                for i in dev_unlocked:
                    ui.updateDevs(i,[2,3])
                ui.returnToMain()
                
        t1 = threading.Thread(target=t1_run, args=())
        t1.start()
        start_time = time.time()
        t2 = threading.Thread(target=timeout_track, args=(ui, 30.0, start_time, t1))
        t2.start()

def writeToSelDrive(button, ui, *args):
    selDrive = ui.driveSel.get_active_text()
    dev_os = platform.system()
    filepath = ''
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    if dev_os == 'Windows':
        filepath = selDrive + ':\\FidelityLock\\' + ui.dev_vendor.get_text() + '_' + ui.dev_sn.get_text() + '.psw'
        if not os.path.isdir('%s:\\FidelityLock' % selDrive):
            os.makedirs('%s:\\FidelityLock' % selDrive)
    elif dev_os == 'Linux':
        filepath = selDrive + '/FidelityLock/' + ui.dev_vendor.get_text() + '_' + ui.dev_sn.get_text() + '.psw'
        if not os.path.isdir('%s/FidelityLock' % selDrive):
            os.makedirs('%s/FidelityLock' % selDrive)
    f = open(filepath, 'w')
    f.write('Model Number: ' + ui.dev_vendor.get_text() + '\nSerial Number: ' + ui.dev_sn.get_text() + '\n')
    f.write('\n\nTimestamp: ' + timestamp + '\nPassword: ' + lockhash.hash_pass(ui.new_pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text()))
    f.close()
    ui.driveWin.destroy()

def passReadUSB(ui, model, sn, *args):
    folder_list = []
    latest_pw = ""
    latest_ts = "0"
    dev_os = platform.system()
    if dev_os == 'Windows':
        for drive in ascii_uppercase:
            if drive != 'C' and os.path.isdir('%s:\\' % drive):
                if os.path.isdir('%s:\\FidelityLock' % drive):
                    folder_list.append(drive)
    elif dev_os == 'Linux':
        txt = os.popen(ui.prefix + 'mount -l').read()
        dev_regex = '/dev/sd[b-z][1-9]?\son\s(/[A-z/]*)\stype'
        drive_list = re.findall(dev_regex, txt)
        for d in drive_list:
            if os.path.isdir('%s/FidelityLock' % d):
                folder_list.append(d)
    if len(folder_list) == 0:
        msg_err('No password files found, check to make sure the USB is properly inserted.')
        return None
    else:
        latest_pw = 'x'
        for i in range(len(folder_list)):
            filename = model + '_' + sn + '.psw'
            if dev_os == 'Windows':
                filepath = folder_list[i] + ":\\FidelityLock\\" + filename
            elif dev_os == 'Linux':
                filepath = folder_list[i] + "/FidelityLock/" + filename
            if os.path.isfile(filepath):
                f = open(filepath, 'r')
                txt = f.read()
                pswReg = 'Timestamp: ([0-9]{14})\nPassword: ([a-z0-9]{64})'
                list = re.findall(pswReg, txt)
                for e in list:
                    ts = e[0]
                    if ts > latest_ts:
                        latest_ts = ts
                        latest_pw = e[1]
                f.close()   
        return latest_pw

def passSaveUSB(ui, *args):
    drive_list = []
    folder_list = []
    dev_os = platform.system()
    if dev_os == 'Windows':
        for drive in ascii_uppercase:
            if drive != 'C' and os.path.isdir('%s:\\' % drive):
                drive_list.append(drive)
                if os.path.isdir('%s:\\FidelityLock' % drive):
                    folder_list.append(drive)
    elif dev_os == 'Linux':
        txt = os.popen(ui.prefix + 'mount -l').read()
        dev_regex = '/dev/sd[b-z][1-9]?\son\s(/[A-z/]*)\stype'
        drive_list = re.findall(dev_regex, txt)
        for d in drive_list:
            if os.path.isdir('%s/FidelityLock' % d):
                folder_list.append(d)
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    if len(folder_list) == 0 and len(drive_list) == 0:
        msg_err('No USB drive detected, please insert a drive and try again.')
    elif len(drive_list) == 1 or len(folder_list) == 1:
    #else:
        if len(folder_list) == 0:
            if dev_os == 'Windows':
                os.makedirs('%s:\\FidelityLock' % drive_list[0])
            elif dev_os == 'Linux':
                os.makedirs('%s/FidelityLock' % drive_list[0])
        f = None
        path = ''
        if dev_os == 'Windows':
            if len(drive_list) == 1:
                path = '' + drive_list[0] + ':\\FidelityLock\\' + ui.dev_vendor.get_text() + '_' + ui.dev_sn.get_text() + '.psw'
            else:
                path = '' + folder_list[0] + ':\\FidelityLock\\' + ui.dev_vendor.get_text() + '_' + ui.dev_sn.get_text() + '.psw'
        elif dev_os == 'Linux':
            if len(drive_list) == 1:
                path = '' + drive_list[0] + '/FidelityLock/' + ui.dev_vendor.get_text() + '_' + ui.dev_sn.get_text() + '.psw'
            else:
                path = '' + folder_list[0] + '/FidelityLock/' + ui.dev_vendor.get_text() + '_' + ui.dev_sn.get_text() + '.psw'
        if path != '':
            f = open(path, 'w')
            f.write('Model Number: ' + ui.dev_vendor.get_text() + '\nSerial Number: ' + ui.dev_sn.get_text() + '\n')
            f.write('Timestamp: ' + timestamp + '\nPassword: ' + lockhash.hash_pass(ui.new_pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text()))
            f.close()
    else:
        ui.driveWin = gtk.Window()
        ui.driveWin.set_border_width(10)
        ui.driveWin.set_default_size(500, 500)
        ui.driveWin.set_title("Audit Log")
        if os.path.isfile('icon.jpg'):
            ui.driveWin.set_icon_from_file('icon.jpg')
        vbox = gtk.VBox()
        ui.driveWin.add(vbox)
        driveInstr = gtk.Label('Select the drive to write to:')
        ui.driveSel = gtk.ComboBoxEntry()
        driveSel_button = gtk.Button('Select')
        driveSel_button.connect('clicked', ui.writeToSelDrive)
        if len(folder_list) > 1:
            for f in folder_list:
                ui.driveSel.append("" + f + ":")
        elif len(drive_list) > 1:
            for d in drive_list:
                ui.driveSel.append("" + d + ":")
        vbox.pack_start(driveInstr, True, False, 0)
        vbox.pack_start(ui.driveSel, True, False, 0)
        vbox.pack_start(driveSel_button, True, False, 0)
        ui.driveWin.show_all()

def openLog(button, ui, *args):
    columns = ["Level", "Date and Time", "Event ID", "Event Description"]
    ui.auditEntries = []
    ui.errorEntries = []
    ui.warnerrEntries = []

    logWin = gtk.Window()
    logWin.set_border_width(10)
    logWin.set_default_size(500, 500)
    logWin.set_title("Audit Log")
    if os.path.isfile('icon.jpg'):
        logWin.set_icon_from_file('icon.jpg')
    vbox = gtk.VBox()
    logWin.add(vbox)
    
    ui.listStore = gtk.ListStore(str, str, int, str)
    
    index = ui.dev_select.get_active()
    ui.devname = ui.devs_list[index]
    password = ""
    if ui.check_pass_rd.get_active():
        password = passReadUSB(ui, ui.dev_vendor.get_text(), ui.dev_sn.get_text())
        if password == None or password == 'x':
            return
    else:
        password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
    
    print password
    txt = os.popen(ui.prefix + "sedutil-cli -n --auditread " + password + " " + ui.devname ).read()
    
    if txt == "" or txt == "Invalid Audit Signature or No Audit Entry log\n":
        ui.msg_err("Invalid Audit Signature or No Audit Entry Log or Read Error")
    else:
        outputLines = txt.split('\n')
        numEntriesLine = outputLines[1]
        entriesRegex = "Total Number of Audit Entries: ([0-9]+)"
        p = re.compile(entriesRegex)
        m0 = p.match(numEntriesLine)
        numEntries = int(m0.group(1))
        logList = outputLines[2:]
        auditRegex = "([0-9]+/[0-9]+/[0-9]+\s+[0-9]+:[0-9]+:[0-9]+)\s+([0-9]+)"
        pattern = re.compile(auditRegex)
        
        for i in range(numEntries):
            m = pattern.match(logList[i])
            dateTime = m.group(1)
            eventID = int(m.group(2))
            eventDes = ui.eventDescriptions[eventID]
            eventLevel = "Information"
            if eventID == 9 or eventID == 14 or eventID == 16 or eventID == 18:
                eventLevel = "Error"
                ui.errorEntries.append((eventLevel, dateTime, eventID, eventDes))
                ui.warnerrEntries.append((eventLevel, dateTime, eventID, eventDes))
            elif eventID == 13 or eventID == 15 or eventID == 17:
                eventLevel = "Warning"
                ui.warnerrEntries.append((eventLevel, dateTime, eventID, eventDes))
            ui.auditEntries.append((eventLevel, dateTime, eventID, eventDes))
        for i in range(len(ui.auditEntries)):
            #print auditEntries[i]
            ui.listStore.append(ui.auditEntries[i])
    
    treeView = gtk.TreeView(model=ui.listStore)
    
    for i in range(len(columns)):
        # cellrenderer to render the text
        cell = gtk.CellRendererText()
        # the column is created
        col = gtk.TreeViewColumn(columns[i], cell, text=i)
        if i < 3:
            col.set_sort_column_id(gtk.SORT_DESCENDING)
            col.set_sort_indicator(True)
        # and it is appended to the treeview
        treeView.append_column(col)
    
    vbox.pack_start(treeView)
    
    halign = gtk.Alignment(1,0,0,0)
    filter_box = gtk.HBox(False, 0)
    
    ui.viewAll_button = gtk.Button('View all entries')
    ui.viewAll_button.connect("clicked", filterLog, ui, ui.auditEntries, 0)
    ui.viewAll_button.set_sensitive(False)
    filter_box.pack_start(ui.viewAll_button, False, False, 5)
    
    ui.viewWarnErr_button = gtk.Button('View Warnings & Errors')
    ui.viewWarnErr_button.connect("clicked", filterLog, ui, ui.warnerrEntries, 1)
    filter_box.pack_start(ui.viewWarnErr_button, False, False, 5)
    
    ui.viewErr_button = gtk.Button('View Errors')
    ui.viewErr_button.connect("clicked", filterLog, ui, ui.errorEntries, 2)
    filter_box.pack_start(ui.viewErr_button, False, False, 5)
    
    #ui.eraseLog_button = gtk.Button('Erase the device\'s entire log')
    #ui.eraseLog_button.connect("clicked", eraseLog, ui)
    #filter_box.pack_start(ui.eraseLog_button, False, False, 5)
    
    halign.add(filter_box)
    vbox.pack_start(halign, False, False, 0)
    
    logWin.show_all()
    
def filterLog(button, ui, entries, mode):
    ui.listStore.clear()
    for i in range(len(entries)):
        ui.listStore.append(entries[i])
    ui.viewAll_button.set_sensitive(mode != 0)
    ui.viewWarnErr_button.set_sensitive(mode != 1)
    ui.viewErr_button.set_sensitive(mode != 2)
    
#def eraseLog(button, ui, *args):
#    password = lockhash.hash_pass(ui.pass_entry.get_text(), ui.dev_sn.get_text(), ui.dev_msid.get_text())
#    status = os.system( ui.prefix + "sedutil-cli -n --auditerase " + password + " " + ui.devname )
#    if status != 0:
#        ui.msg_err('Error while attempting to erase the audit log')
#    else:
#        ui.listStore.clear()
#        ui.auditEntries = []
#        ui.errorEntries = []
#        ui.warnerrEntries = []
#        ui.msg_ok('Audit Log erased successfully')

def timeout_track(ui, max_time, start_time, op_thread):
    status = 0
    done = False
    while not done:
        if op_thread.isAlive():
            curr_time = time.time()
            elapsed_time = curr_time - start_time
            if elapsed_time >= max_time:
                done = True
        else:
            done = True
    
    gobject.idle_add(timeout_cleanup, ui, max_time, start_time, op_thread)

def timeout_cleanup(ui, max_time, start_time, op_thread):
    if op_thread.isAlive():
        curr_time = time.time()
        elapsed_time = curr_time - start_time
        if elapsed_time >= max_time:
            op_thread.join(0.0)
            ui.msg_err("Operation timed out.")
    
    ui.stop_spin()