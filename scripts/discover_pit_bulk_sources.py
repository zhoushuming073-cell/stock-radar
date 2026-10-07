"""Capture public bulk source metadata and small files, with immutable receipts."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from benchmark_pit_sources import Cache

PINS = {
    'jadchaar/sec-cik-mapper':'7883b83389836f9bba9bdfe53031467235746334',
    'datasets/nasdaq-listings':'3bfa59eee648599edb0f1f7c33755cf3790038be',
    'supermodo/us-markets-timemachine':'9359ff371150122f326d435495abec725d82de84',
    'tenicho/data-cleaning':'a34d6cfa3f5313bdb77c76a57d305382bc1c54dd',
    'Stonks/tickers':'30ab4744279f6d34d20a438ec98413db96a53f69',
    'QuantConnect/Lean.DataSource.SEC':'dcba1ba901e854f67119c0c1a57d8ac8bbcd0c16',
}


def main():
    root=Path.cwd();cache=Cache(root/'data/pit/raw/source-breakthrough')
    urls=[]
    for repo,pin in PINS.items():
        urls += [f'https://api.github.com/repos/{repo}/git/trees/{pin}?recursive=1',
                 f'https://api.github.com/repos/{repo}/commits/{pin}',
                 f'https://raw.githubusercontent.com/{repo}/{pin}/README.md']
    for path in ('LICENSE','mappings/stocks/mappings.csv'):
        urls.append(f'https://raw.githubusercontent.com/jadchaar/sec-cik-mapper/{PINS["jadchaar/sec-cik-mapper"]}/{path}')
    urls += [f'https://raw.githubusercontent.com/tenicho/data-cleaning/{PINS["tenicho/data-cleaning"]}/.gitignore',
             f'https://raw.githubusercontent.com/supermodo/us-markets-timemachine/{PINS["supermodo/us-markets-timemachine"]}/data/nasdaq/NOTICE.md',
             f'https://api.github.com/repos/datasets/nasdaq-listings/commits?path=data/nasdaq-listed.csv&until=2025-09-08T23:59:59Z&per_page=100',
             f'https://api.github.com/repos/jadchaar/sec-cik-mapper/commits?path=mappings/stocks/mappings.csv&since=2024-09-25T00:00:00Z&until=2025-09-08T23:59:59Z&per_page=100']
    for q in ('2024q2','2024q3','2024q4','2025q1','2025q2','2025q3'):
        urls.append('https://www.sec.gov/files/investment/13flist'+q+'.txt')
    for dataset in ('defeatbeta/yahoo-finance-data','paperswithbacktest/Stocks-Daily-Price',
                    'paperswithbacktest/AlphaVantage-Stocks-Daily-ListingStatus','finsaber-team/FINSABER-reproduce',
                    'yolo22/stock-pit-archives'):
        urls.append('https://huggingface.co/api/datasets/'+dataset)
    urls += ['https://api.finra.org/data/group/otcMarket/name/OTCDAILYLIST?limit=5',
             'https://www.alphavantage.co/query?function=LISTING_STATUS&date=2024-09-30&state=active&apikey=demo',
             'https://www.dolthub.com/api/v1alpha1/graziek9/Stock_Data/main?q=SHOW+TABLES',
             'https://www.dolthub.com/api/v1alpha1/Liquidata/stock-tickers/master?q=SHOW+TABLES',
             'https://iangow.github.io/sec_submissions/data/']
    def fetch(url):
        try:
            _,receipt=cache.get(url)
            print(receipt['status'],url,flush=True)
            return receipt
        except Exception as e:return {'url':url,'error':str(e),'status':None}
    with ThreadPoolExecutor(max_workers=4) as pool:receipts=list(pool.map(fetch,urls))
    out=root/'data/pit/source-breakthrough/discovery-receipts.json'
    out.write_text(json.dumps({'pins':PINS,'receipts':receipts},indent=2),encoding='utf-8')


if __name__=='__main__':main()
