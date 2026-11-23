"""RBNU AF scale sweep with SCANFI 30 m neighbourhood metrics.

Aspatial terms stay the kNN product used by the estate; the neighbourhood terms are
recomputed from SCANFI v2 at 30 m for radius half-widths 30, 60, 120, 250, 500 m.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from pyproj import Transformer
import patsy
import statsmodels.api as sm

ROOT=Path("/srv/shared-data/gep/wbi-birds")
sys.path.insert(0,str(ROOT/"reference/wbi-main/scripts"))
from fit_composition_probe import build

SC=Path("/srv/shared-data/gep/jupyterhub16-projects/clews-c2070-fresh/data/raw/scanfi/v2")
AGE=SC/"SCANFI_age_median_2025_v2_20260119.tif"
BIO=SC/"SCANFI_att_biomass_2025_v2_20260119.tif"
BROAD=SC/"SCANFI_spsCC_broadleaf_2025_v2_20260119.tif"
RADII=(1,2,4,8,17,34,67)  # 30..2010 m radius at 30 m
NAMES={1:"30m",2:"60m",4:"120m",8:"240m",17:"510m",34:"1020m",67:"2010m"}
MAXR=67

def poisson_dev(y,mu):
    y=np.asarray(y,float); mu=np.maximum(np.asarray(mu,float),1e-9)
    with np.errstate(divide="ignore",invalid="ignore"):
        t=np.where(y>0,y*np.log(y/mu),0.0)
    return 2*np.sum(t-(y-mu))

def evaluate(df, formula, folds=5):
    off=(np.log(df.duration.fillna(1.0))+np.log1p(df.distance.fillna(0.0))
         +np.log(df.observers.fillna(1.0).clip(lower=1))).to_numpy()
    y,X=patsy.dmatrices(f"rebnut ~ {formula}",df,return_type="dataframe")
    m=sm.GLM(y,X,family=sm.families.Poisson(),offset=off).fit(maxiter=80)
    cell=((df.lat//0.5).astype(int)*10000+(df.lon//0.5).astype(int)).to_numpy()
    u=np.unique(cell); rng=np.random.default_rng(42); rng.shuffle(u); dev=0.0
    for k in range(folds):
        test=np.isin(cell,u[k::folds]); train=~test
        if test.sum()==0 or train.sum()==0: continue
        f=sm.GLM(y[train],X[train],family=sm.families.Poisson(),offset=off[train]).fit(maxiter=80)
        mu=np.exp(np.clip(np.asarray(X[test]@f.params)+off[test],-30,30))
        dev+=poisson_dev(np.asarray(y[test]).ravel(),mu)
    return float(m.aic), float(dev/len(df))

def metrics(age,bio,row,col):
    if age.shape[0]<2*MAXR+1 or age.shape[1]<2*MAXR+1:
        return None
    age=age.astype(float); bio=bio.astype(float)
    valid=(age>0)&(bio>0)&(age!=32767)&(bio!=32767)
    forest=valid
    early=forest&(age<40)
    b=np.zeros_like(forest,dtype=np.float32)
    b[:-1,:]+=forest[:-1,:]!=forest[1:,:]; b[1:,:]+=forest[1:,:]!=forest[:-1,:]
    b[:,:-1]+=forest[:,:-1]!=forest[:,1:]; b[:,1:]+=forest[:,1:]!=forest[:,:-1]
    out={}
    for r in RADII:
        sl=slice(MAXR-r,MAXR+r+1)
        win=np.ones((2*r+1,2*r+1))
        out[f"forest_{NAMES[r]}"]=float(forest[sl,sl].mean())
        out[f"early_{NAMES[r]}"]=float(early[sl,sl].mean())
        out[f"edge_{NAMES[r]}"]=float((b[sl,sl]>0).mean())
    return out

if __name__=="__main__":
    n=int(sys.argv[1]) if len(sys.argv)>1 else 5000
    frame=build()
    samples=np.load(ROOT/"campaigns/ws4-five-tsa-2026-11/knn-v0/samples-study-area.npz",allow_pickle=True)
    frame=frame.merge(pd.DataFrame({"event":samples["checklist_id"].astype(str),"lat":samples["latitude"],"lon":samples["longitude"],"year":samples["year"]}),on="event",how="inner")
    min_year=int(sys.argv[2]) if len(sys.argv)>2 else 0
    max_year=int(sys.argv[3]) if len(sys.argv)>3 else 9999
    if min_year:
        frame=frame[frame.year>=min_year]
        print("year filter",min_year,"rows",len(frame),flush=True)
    if max_year<9999:
        frame=frame[frame.year<=max_year]
        print("max year",max_year,"rows",len(frame),flush=True)
    frame=frame.dropna(subset=["rebnut","soft_vol","hard_vol","age","duration","distance","observers","lat","lon"])
    frame["log_soft"]=np.log1p(frame.soft_vol); frame["log_hard"]=np.log1p(frame.hard_vol)
    frame["year_c"]=(frame.year-frame.year.mean())/max(frame.year.std(),1e-9)
    rng=np.random.default_rng(42)
    frame=frame.sample(n=min(n,len(frame)),random_state=42).reset_index(drop=True)
    print("rows",len(frame),flush=True)
    with rasterio.open(AGE) as a, rasterio.open(BIO) as b, rasterio.open(BROAD) as br:
        tr=Transformer.from_crs("EPSG:4326",a.crs,always_xy=True)
        xs,ys=tr.transform(frame.lon.to_numpy(),frame.lat.to_numpy())
        cols=np.floor((xs-a.transform.c)/a.transform.a).astype(int)
        rows=np.floor((ys-a.transform.f)/a.transform.e).astype(int)
        recs=[]; idxs=[]; t=time.time(); ok=0
        for i,(r,c) in enumerate(zip(rows,cols)):
            if r<MAXR or c<MAXR or r>=a.height-MAXR or c>=a.width-MAXR: continue
            w=Window(c-MAXR,r-MAXR,2*MAXR+1,2*MAXR+1)
            age=a.read(1,window=w); bio=b.read(1,window=w)
            m=metrics(age,bio,r,c)
            if m is None: continue
            bl=float(br.read(1,window=Window(c,r,1,1))[0,0])
            if bl==br.nodata or bl<0 or bl>100: bl=float("nan")
            elif bl>1: bl=bl/100.0
            total=float(bio[MAXR,MAXR]); agec=float(age[MAXR,MAXR])
            m.update({"sc_biomass":total,"sc_broadleaf":bl,"sc_age":agec,
                      "sc_soft":total*(1.0-bl) if np.isfinite(bl) else np.nan,
                      "sc_hard":total*bl if np.isfinite(bl) else np.nan})
            recs.append(m); idxs.append(i); ok+=1
            if ok%1000==0: print(ok,round(time.time()-t),flush=True)
        print("sampled",ok,round(time.time()-t),flush=True)
    md=pd.DataFrame(recs); frame=frame.iloc[idxs].reset_index(drop=True)
    frame=pd.concat([frame,md],axis=1)
    frame.to_csv(ROOT/"fvsbc-work/rbnu-scale-frame.csv",index=False)
    out=Path("/srv/shared-data/gep/wbi-birds/fvsbc-work/rbnu-scale-sweep.csv")
    res=[]
    scframe=frame.dropna(subset=["sc_soft","sc_hard","sc_age"]).copy()
    scframe["sc_log_soft"]=np.log1p(scframe.sc_soft); scframe["sc_log_hard"]=np.log1p(scframe.sc_hard)
    print("scanfi rows",len(scframe),"of",len(frame),flush=True)
    yt=" + year_c" if os.environ.get("YEAR_TERM")=="1" else ""
    base="log_soft + log_hard + age"+yt
    scbase="sc_log_soft + sc_log_hard + sc_age"+yt
    aic,cv=evaluate(frame,base); res.append(("aspatial-knn",aic,cv)); print("aspatial-knn",round(aic,1),round(cv,5),flush=True)
    if len(scframe)>0:
        aic,cv=evaluate(scframe,scbase); res.append(("aspatial-scanfi",aic,cv)); print("aspatial-scanfi",round(aic,1),round(cv,5),flush=True)
    for r in RADII:
        nme=NAMES[r]; formula=f"{base} + forest_{nme} + edge_{nme} + early_{nme}"
        aic,cv=evaluate(frame,formula); res.append((nme,aic,cv))
        print(nme,round(aic,1),round(cv,5),flush=True)
    if len(scframe)>0:
        for r in RADII:
            nme=NAMES[r]; formula=f"{scbase} + forest_{nme} + edge_{nme} + early_{nme}"
            aic,cv=evaluate(scframe,formula); res.append(("scanfi-"+nme,aic,cv))
            print("scanfi-"+nme,round(aic,1),round(cv,5),flush=True)
    pd.DataFrame(res,columns=["scale","aic","cv_per_row"]).to_csv(out,index=False)
    print("wrote",out,flush=True)
