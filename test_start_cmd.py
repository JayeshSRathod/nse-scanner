from nse_telegram_polling import handle_command, save_scan_results
from datetime import date
import pandas as pd

# prepare test data
arr=[{'symbol':'ABC','score':10}]
df=pd.DataFrame(arr)
save_scan_results(df,date.today())

for cmd in ['/start','/start@mybot','/start@AnotherBot']:
    print('command=',cmd)
    res=handle_command('test',cmd,is_callback=True)
    print(res)
