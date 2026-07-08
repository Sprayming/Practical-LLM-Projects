import subprocess,time,requests
p=subprocess.Popen([chr(117)+chr(118)+chr(105)+chr(99)+chr(111)+chr(114)+chr(110),chr(97)+chr(112)+chr(112)+chr(46)+chr(109)+chr(97)+chr(105)+chr(110)+chr(58)+chr(97)+chr(112)+chr(112),chr(45)+chr(45)+chr(104)+chr(111)+chr(115)+chr(116),chr(49)+chr(50)+chr(55)+chr(46)+chr(48)+chr(46)+chr(48)+chr(46)+chr(49),chr(45)+chr(45)+chr(112)+chr(111)+chr(114)+chr(116),chr(56)+chr(48)+chr(48)+chr(48)],cwd=chr(68)+chr(58)+chr(47)+chr(103)+chr(105)+chr(116)+chr(47)+chr(114)+chr(105)+chr(100)+chr(101)+chr(111)+chr(112)+chr(115)+chr(45)+chr(97)+chr(105)+chr(47)+chr(98)+chr(97)+chr(99)+chr(107)+chr(101)+chr(110)+chr(100),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(5)
BASE="http://127.0.0.1:8000"
r=requests.get(BASE+"/api/data/upload",files={"file":("orders.csv",open("D:/git/rideops-ai/data/sample/orders_sample.csv","rb"))})
d=r.json()