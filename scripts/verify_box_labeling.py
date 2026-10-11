import argparse,json
from radar.box_labeling.verify import verify_bundle

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args()
    print(json.dumps(verify_bundle(a.directory),indent=2))
