import datetime

# 6 июня 2025 12:16:10

stime = "12:16:10 6/6/2025"
print(datetime.datetime.strptime(stime, "%H:%M:%S %d/%m/%Y").timestamp())