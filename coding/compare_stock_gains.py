# filename: compare_stock_gains.py

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# Get the current date
now = datetime.now()
print("Current date:", now.strftime("%Y-%m-%d"))

# Define the stock tickers
tickers = ['META', 'TSLA']

# Get the stock data for the year-to-date period
stock_data = pd.DataFrame()
for ticker in tickers:
    url = f'https://finance.yahoo.com/quote/{ticker}/history?period1=1643654400&period2=1675260800&interval=1d&filter=history'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'class': 'W(100%)'})
    rows = table.find_all('tr')
    data = []
    for row in rows[1:]:
        cols = row.find_all('td')
        cols = [col.text.strip() for col in cols]
        data.append([ticker] + cols)
    df = pd.DataFrame(data, columns=['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume'])
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    stock_data = pd.concat([stock_data, df], axis=1)

# Calculate the year-to-date gain
ytd_gain = (stock_data.pct_change(periods=0)['Close'][-1] * 100).round(2)
print("\nYear-to-date gain for META:", ytd_gain[0], "%")
print("Year-to-date gain for TESLA:", ytd_gain[1], "%")

# Check if META or TESLA has a higher year-to-date gain
if ytd_gain[0] > ytd_gain[1]:
    print("\nMETA has a higher year-to-date gain than TESLA.")
elif ytd_gain[0] < ytd_gain[1]:
    print("\nTESLA has a higher year-to-date gain than META.")
else:
    print("\nMETA and TESLA have the same year-to-date gain.")