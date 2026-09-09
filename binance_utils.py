import ccxt
import cst

def get_price_precision(sym):
    if("/" not in sym):
        sym = sym.replace("USDT", "/USDT")
    
    exchange = ccxt.binance({
            'apiKey': cst.key_binance,
            'secret': cst.secret_binance,
            'options': {
                'defaultType': 'future',
                'fetchCurrencies': False,          # [A2] tránh gọi /sapi getall (signed) khi load_markets
                'adjustForTimeDifference': True,   # [A2] tự đồng bộ clock -> hết lỗi -1021
                'recvWindow': 60000,               # [A2+Fix2] nới cửa sổ timestamp lên max 60s
            }
        })

    
    markets = exchange.load_markets()

    
    symbol = f'{sym}:USDT'

    
    if symbol in markets:
        
        market = markets[symbol]

        
        price_precision = market['precision']['price']
        amount_precision = market['precision']['amount']
        return int(price_precision)
        
        
    else:
        print(f"Cặp giao dịch {symbol} không tồn tại trên Binance futures.")

# [ĐÃ XOÁ] Dòng gọi thử get_price_precision("PEOPLE/USDT") ở cấp module.
# Nó khiến MỌI bot import binance_utils đều tạo exchange + load_markets khi khởi
# động (chậm vài giây + tốn 1 lượt gọi API vô ích).