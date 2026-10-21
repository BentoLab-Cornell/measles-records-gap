"""
Children outside school vaccination reporting: county-level estimate for the US.

For every county, compares Census SAIPE estimates of resident children aged 5-17
(2022) with K-12 enrollment in public schools (NCES CCD 2022-23) and private
schools (NCES PSS 2021-22). Two measures:

  gap      = 1 - (public K-12 + allocated virtual + private K-12) / children 5-17
             -> children who appear in no public or private school count
  outside  = gap + Amish and Mennonite school enrollment / children 5-17
             -> also counts schools that often sit outside vaccination surveys

All inputs are public and aggregate. Run:  python gap_analysis.py
Outputs go to ./output/
"""
import io, os, time, zipfile, concurrent.futures as cf
import numpy as np, pandas as pd, requests
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

API = "https://educationdata.urban.org/api/v1"
PSS_URL = "https://nces.ed.gov/surveys/pss/zip/pss2122_pu_csv.zip"
YEAR = 2022
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
DATA = os.path.join(HERE, "data")
PSS_LOCAL = os.path.join(DATA, "pss2122_pu_csv.zip")
API_CACHE = os.path.join(DATA, f"api_cache_{YEAR}.pkl")
FIPS = [1,2,4,5,6,8,9,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,
        30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47,48,49,50,51,53,54,55,56]
NYC = {"36005","36047","36061","36081","36085"}   # NYC is one SAIPE district
MIN_CHILDREN = 1000
PLAIN_ORIENT = {"3", "24"}                       # PSS orientation: 3 Amish, 24 Mennonite

def get_all(url):
    out = []
    while url:
        for attempt in range(5):
            try:
                r = requests.get(url, timeout=120); r.raise_for_status(); j = r.json(); break
            except Exception:
                time.sleep(3 * (attempt + 1)); j = None
        if j is None: raise RuntimeError(f"failed: {url}")
        out += j["results"]; url = j.get("next")
    return out

def fetch_state(f):
    q = f"?fips={f}"
    return (get_all(f"{API}/school-districts/saipe/{YEAR}/{q}"),
            get_all(f"{API}/school-districts/ccd/enrollment/{YEAR}/grade-99/{q}"),
            get_all(f"{API}/school-districts/ccd/enrollment/{YEAR}/grade-pk/{q}"),
            get_all(f"{API}/school-districts/ccd/directory/{YEAR}/{q}"),
            get_all(f"{API}/schools/ccd/directory/{YEAR}/{q}"))

def unit(cc): return "36NYC" if cc in NYC else cc

def main():
    os.makedirs(OUT, exist_ok=True); os.makedirs(DATA, exist_ok=True)
    if os.path.exists(API_CACHE):
        parts = pd.read_pickle(API_CACHE)
    else:
        parts = [[] for _ in range(5)]
        with cf.ThreadPoolExecutor(8) as ex:
            for res in ex.map(fetch_state, FIPS):
                for i, r in enumerate(res): parts[i] += r
        pd.to_pickle(parts, API_CACHE)
    saipe, enr, pk, lea, sch = (pd.DataFrame(p) for p in parts)
    for df in (saipe, enr, pk, lea, sch): df["leaid"] = df.leaid.astype(str).str.zfill(7)
    lea["county_code"] = lea.county_code.astype(str).str.zfill(5)
    sch["county_code"] = sch.county_code.astype(str).str.zfill(5)

    # children 5-17 by county (district -> county of district office)
    s = saipe.merge(lea.drop_duplicates("leaid")[["leaid", "county_code"]], on="leaid", how="inner")
    s["unit"] = s.county_code.map(unit)
    pop = s.groupby("unit").est_population_5_17.sum()

    # public K-12: school enrollment scaled by district K-12 share (drops pre-K)
    e = enr.set_index("leaid").enrollment.clip(lower=0)
    p = pk.set_index("leaid").enrollment.clip(lower=0).reindex(e.index).fillna(0)
    k12frac = ((e - p) / e).where(e > 0).clip(0, 1).fillna(1)
    sch["enrollment"] = pd.to_numeric(sch.enrollment, errors="coerce").clip(lower=0).fillna(0)
    sch["k12"] = sch.enrollment * sch.leaid.map(k12frac).fillna(1)
    sch["virtual_school"] = sch.virtual.isin([1, 2])      # exclusively / primarily virtual
    sch["unit"] = sch.county_code.map(unit); sch["state"] = sch.county_code.str[:2]
    phys = sch[~sch.virtual_school].groupby("unit").k12.sum()
    virt_state = sch[sch.virtual_school].groupby("state").k12.sum()

    # private K-12 (survey-weighted), PSS 2021-22
    if not os.path.exists(PSS_LOCAL):
        content = requests.get(PSS_URL, timeout=300).content
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise SystemExit(f"NCES did not return a zip file (site may be under maintenance). "
                             f"Download {PSS_URL} by hand and save it as {PSS_LOCAL}.")
        open(PSS_LOCAL, "wb").write(content)
    z = zipfile.ZipFile(PSS_LOCAL)
    pss = pd.read_csv(z.open([n for n in z.namelist() if n.endswith(".csv")][0]),
                      usecols=["PFNLWT", "PSTANSI", "PCNTY22", "NUMSTUDS", "ORIENT"], dtype=str)
    pss["w"] = pd.to_numeric(pss.PFNLWT, errors="coerce") * pd.to_numeric(pss.NUMSTUDS, errors="coerce")
    pss["county_code"] = pss.PSTANSI.str.zfill(2) + pss.PCNTY22.str[:3]   # PCNTY22 = county(3)+state(2)
    pss["unit"] = pss.county_code.map(unit)
    priv = pss.groupby("unit").w.sum()
    plain = pss[pss.ORIENT.isin(PLAIN_ORIENT)].groupby("unit").w.sum()

    C = (pd.DataFrame({"children_5_17": pop}).join(phys.rename("public_k12"))
         .join(priv.rename("private_k12")).join(plain.rename("amish_mennonite_k12")).fillna(0))
    C["state"] = C.index.str[:2]
    # statewide virtual schools: allocate to counties by share of state children
    C["virtual_k12_alloc"] = (C.children_5_17 / C.groupby("state").children_5_17.transform("sum")
                              * C.state.map(virt_state).fillna(0))
    acc = C.public_k12 + C.virtual_k12_alloc + C.private_k12
    C["gap"] = 1 - acc / C.children_5_17
    C["outside"] = C.gap + C.amish_mennonite_k12 / C.children_5_17
    C = C[C.children_5_17 >= MIN_CHILDREN].copy()
    for v in ("gap", "outside"):
        C[f"{v}_pctile"] = C[v].rank(pct=True) * 100
        st = (C[v] * C.children_5_17).groupby(C.state).sum() / C.groupby("state").children_5_17.sum()
        C[f"{v}_state"] = C.state.map(st)
    C.round(4).to_csv(os.path.join(OUT, "all_county_gap_2022.csv"), index_label="county_fips")

    outbreaks = {"42071": ("Lancaster, PA (2026)", True), "42087": ("Mifflin, PA (2026)", True),
                 "48165": ("Gaines, TX (2025)", True), "39075": ("Holmes, OH (2014)", True),
                 "39083": ("Knox, OH (2014)", True), "45083": ("Spartanburg, SC (2025-26)", False),
                 "04015": ("Mohave, AZ (2025-26)", False), "49053": ("Washington, UT (2025-26)", False),
                 "36087": ("Rockland, NY (2018-19)", False), "36NYC": ("New York City (2018-19)", False),
                 "27053": ("Hennepin, MN (2017)", False), "53011": ("Clark, WA (2019)", False)}
    T = C.loc[list(outbreaks)].copy()
    T.insert(0, "county", [outbreaks[k][0] for k in T.index])
    T.insert(1, "amish_mennonite_outbreak", [outbreaks[k][1] for k in T.index])
    T.round(4).to_csv(os.path.join(OUT, "outbreak_county_gap.csv"), index_label="county_fips")

    D = T.sort_values("outside_pctile"); y = np.arange(len(D))
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    ax.axvspan(90, 100, color="#EFE3DF", lw=0)
    for yi, (_, r) in zip(y, D.iterrows()):
        c = "#B5432F" if r.amish_mennonite_outbreak else "#5B7A99"
        ax.plot([0, r.outside_pctile], [yi, yi], color=c, lw=0.8, alpha=0.5)
        ax.scatter(r.outside_pctile, yi, s=34, color=c, edgecolor="white", lw=0.5, zorder=3)
        lab = "<0%" if r.outside < 0 else f"{r.outside*100:.0f}%"
        right = r.outside_pctile >= 88
        ax.text(r.outside_pctile + (-2 if right else 1.5), yi, lab, va="center",
                ha="right" if right else "left", fontsize=6.5, color=c)
    ax.set_yticks(y); ax.set_yticklabels(D.county, fontsize=7)
    ax.set_xlim(0, 101); ax.set_xlabel("National county percentile: share of children aged 5-17 outside reporting schools", fontsize=8)
    ax.set_title("Amish and Mennonite outbreak counties rank above the 90th percentile", loc="left", fontsize=8)
    ax.tick_params(axis="x", labelsize=7)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color="#B5432F", label="Amish or Mennonite community outbreak"),
                       Line2D([], [], marker="o", ls="", color="#5B7A99", label="Other outbreak")],
              loc="lower right", bbox_to_anchor=(0.86, 0.0), frameon=False, fontsize=7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "gap_percentiles.png"), dpi=300)
    print(T[["county", "gap", "gap_pctile", "outside", "outside_pctile", "outside_state"]].round(3).to_string())
    print(f"\n{len(C)} counties with >= {MIN_CHILDREN} children aged 5-17")

if __name__ == "__main__":
    main()
