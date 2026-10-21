# Children outside school vaccination reporting

US measles prevention is targeted with school vaccination records. This repository estimates, for every US county, how many school-age children appear in no school count at all, and how many attend Amish or Mennonite schools, which often sit outside state vaccination surveys.

It is the preliminary analysis behind a pilot proposal from the [Bento Lab](https://www.anabento.io) at Cornell University. All inputs are public and aggregate.

![County percentiles](output/gap_percentiles.png)

## Main result

Using data from 2021–23, before the 2025–26 outbreaks:

| County | Children in no school count | State | Including Amish and Mennonite schools | National percentile |
|---|---|---|---|---|
| Lancaster, PA (2026 outbreak) | 15.7% | 3.5% | 21.0% | 94th |
| Mifflin, PA (2026 outbreak) | <0% | 3.5% | 21.0% | 94th |
| Gaines, TX (2025 outbreak) | 20.7% | 0.9% | 38.3% | 99th |
| Spartanburg, SC (2025–26 outbreak) | 3.8% | 1.1% | 3.8% | 44th |

Percentiles are among the 2,687 counties with at least 1,000 children aged 5–17. The 2014 Ohio counties (Holmes, Knox) are shown in the figure for comparison, but their data postdate the outbreak. Full results are in `output/outbreak_county_gap.csv` and `output/all_county_gap_2022.csv`.

## Method

For each county:

- **Children aged 5–17**: Census Small Area Income and Poverty Estimates (SAIPE), 2022, by school district, assigned to the county of the district office.
- **Public K–12 enrollment**: NCES Common Core of Data, 2022–23, by school. Pre-K is removed using each district's pre-K share. Exclusively or primarily virtual schools are removed from their headquarters county and spread across the state in proportion to children.
- **Private K–12 enrollment**: NCES Private School Survey, 2021–22, survey-weighted. Amish (orientation code 3) and Mennonite (code 24) schools are identified separately.
- New York City's five boroughs are combined, because SAIPE treats the city as one district.

Two measures:

- `gap` = 1 − (public + virtual + private enrollment) / children 5–17. Children who appear in no school count: mostly homeschooled children, children in schools missing from the private school survey, and children not enrolled.
- `outside` = `gap` + Amish and Mennonite enrollment / children 5–17.

SAIPE and CCD data are retrieved through the [Urban Institute Education Data API](https://educationdata.urban.org). The private school file comes from [NCES](https://nces.ed.gov/surveys/pss/pssdata.asp).

## Limitations

- County-level estimates are noisy. Children who attend school in another county produce negative values in some counties (shown as <0%).
- Census ages 5–17 and grades K–12 do not line up exactly.
- The private school survey misses some small schools. Survey weights partly correct for this.
- Whether Amish and Mennonite schools report vaccinations varies by state and school. The `outside` measure assumes they do not.
- This is a screening measure of where vaccination records are incomplete, not an estimate of vaccination coverage.

## Reproduce

```
pip install -r requirements.txt
python gap_analysis.py
```

The first run downloads about 120,000 records from the Education Data API (around 5 minutes) and caches them in `data/`. If the NCES site is unavailable, download `pss2122_pu_csv.zip` from the link above and save it as `data/pss2122_pu_csv.zip`.

Results name counties and school districts, never communities or individuals.

## License and citation

Code is released under the MIT License. Input data are public US government statistics. See `CITATION.cff` to cite this repository.
