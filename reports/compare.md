# Metriport public HCC map vs CMS 2026

Inputs: [`hcc-map.ts` at `e1f26d5`](https://github.com/metriport/metriport/blob/e1f26d504cb9d132d66a7a9607ffb199be759168/packages/core/src/external/fhir/shared/hcc-map.ts) (sha256 `8ddc36082f70`), [CMS 2026 mapping](https://www.cms.gov/files/zip/2026-midyear-final-icd-10-mappings.zip) (sha256 `1143bc102311`), [CMS 2025 mapping](https://www.cms.gov/files/zip/2025-midyear/final-icd-10-mappings.zip-0) (sha256 `3fd8a313d847`). Regenerate with `make compare`.

## Summary

- The public map has 11,184 ICD-10-CM codes.
- CMS 2026 gives a payable V28 HCC to 8,019 codes.
- **231 of those codes are not in the public map.** 134 are brand new ICD-10-CM codes for FY2026. The other 97 were added to ICD-10-CM for FY2025.
- 22 codes in the map carry a V28 HCC but are not valid ICD-10-CM codes in FY2025 or FY2026. They are older parent codes that were split into more specific codes. 18 of them were split on Oct 1, 2024, and 49 of the new codes they were split into are among the missing codes above.
- Codes that are in the map agree with CMS 2026 on V28: 0 differences.
- Codes that are in the map agree with CMS 2025 on V24: 0 differences.
- 2,255 codes in the map carry a V24 HCC and no V28 HCC. Community V24 is not one of the models in the CMS 2026 file.
- 26 HCC numbers are used by both V24 and V28 in the map. 23 of them share no ICD-10-CM code at all between the two versions, so the number alone does not say which condition group it is.

So the map matches CMS for the codes CMS still lists, apart from the split parent codes listed below. The main gap is the newer codes from the Oct 1, 2024 and Oct 1, 2025 code updates, which a refresh from the 2026 CMS file closes.

## Missing codes by status

| Status | Codes |
|---|---:|
| in the CMS 2025 file with a V28 HCC | 97 |
| new ICD-10-CM code in FY2026 (not in the CMS 2025 file) | 134 |

When each missing code was added to ICD-10-CM (from the official addenda files):

| Added | Codes |
|---|---:|
| FY2025 (Oct 1, 2024) | 97 |
| FY2026 (Oct 1, 2025) | 134 |

Most common ICD-10-CM categories among them: L98 (112), F50 (18), C86 (14), C88 (12), C82 (9), C83 (9), C84 (8), G35 (8).

Examples (full list in `missing_v28_codes.csv`):

| Code | Description | V28 HCC 2026 | Status |
|---|---|---:|---|
| C50A0 | Malignant inflammatory neoplasm of unspecified breast | 23 | new ICD-10-CM code in FY2026 (not in the CMS 2025 file) |
| C50A1 | Malignant inflammatory neoplasm of right breast | 23 | new ICD-10-CM code in FY2026 (not in the CMS 2025 file) |
| C50A2 | Malignant inflammatory neoplasm of left breast | 23 | new ICD-10-CM code in FY2026 (not in the CMS 2025 file) |
| C810A | Nodular lymphocyte predominant Hodgkin lymphoma, in remission | 21 | in the CMS 2025 file with a V28 HCC |
| C820A | Follicular lymphoma grade I, in remission | 21 | in the CMS 2025 file with a V28 HCC |
| C830A | Small cell B-cell lymphoma, in remission | 21 | in the CMS 2025 file with a V28 HCC |
| C840A | Mycosis fungoides, in remission | 20 | in the CMS 2025 file with a V28 HCC |
| C851A | Unspecified B-cell lymphoma, in remission | 21 | in the CMS 2025 file with a V28 HCC |
| C8600 | Extranodal NK/T-cell lymphoma, nasal type not having achieved remission | 20 | in the CMS 2025 file with a V28 HCC |
| E66813 | Obesity, class 3 | 48 | in the CMS 2025 file with a V28 HCC |

## Older codes that were split

These codes are in the map with a V28 HCC, but they are not in the CMS 2026 file and are not valid ICD-10-CM codes in FY2025 or FY2026. Each one was replaced by more specific codes. Full list in `split_parent_codes.csv`.

| Code | Description | Map V28 HCC | Removed from ICD-10-CM | Replaced by (FY2026) | Of those, missing from map |
|---|---|---:|---|---|---:|
| C8339 | Diffuse large B-cell lymphoma, extranodal and solid organ sites | 20 | FY2025 (Oct 1, 2024) | C83390, C83398 | 2 |
| C860 | Extranodal NK/T-cell lymphoma, nasal type | 20 | FY2025 (Oct 1, 2024) | C8600, C8601 | 2 |
| C861 | Hepatosplenic T-cell lymphoma | 20 | FY2025 (Oct 1, 2024) | C8610, C8611 | 2 |
| C862 | Enteropathy-type (intestinal) T-cell lymphoma | 20 | FY2025 (Oct 1, 2024) | C8620, C8621 | 2 |
| C863 | Subcutaneous panniculitis-like T-cell lymphoma | 19 | FY2025 (Oct 1, 2024) | C8630, C8631 | 2 |
| C864 | Blastic NK-cell lymphoma | 19 | FY2025 (Oct 1, 2024) | C8640, C8641 | 2 |
| C865 | Angioimmunoblastic T-cell lymphoma | 19 | FY2025 (Oct 1, 2024) | C8650, C8651 | 2 |
| C866 | Primary cutaneous CD30-positive T-cell proliferations | 20 | FY2025 (Oct 1, 2024) | C8660, C8661 | 2 |
| C880 | Waldenstrom macroglobulinemia | 21 | FY2025 (Oct 1, 2024) | C8800, C8801 | 2 |
| C882 | Heavy chain disease | 21 | FY2025 (Oct 1, 2024) | C8820, C8821 | 2 |
| C883 | Immunoproliferative small intestinal disease | 21 | FY2025 (Oct 1, 2024) | C8830, C8831 | 2 |
| C884 | Extranodal marginal zone B-cell lymphoma of mucosa-associated lymphoid tissue [MALT-lymphoma] | 21 | FY2025 (Oct 1, 2024) | C8840, C8841 | 2 |
| C888 | Other malignant immunoproliferative diseases | 21 | FY2025 (Oct 1, 2024) | C8880, C8881 | 2 |
| C889 | Malignant immunoproliferative disease, unspecified | 21 | FY2025 (Oct 1, 2024) | C8890, C8891 | 2 |
| E340 | Carcinoid syndrome | 17 | FY2025 (Oct 1, 2024) | E3400, E3401, E3409 | 3 |
| F5001 | Anorexia nervosa, restricting type | 153 | FY2025 (Oct 1, 2024) | F50010, F50011, F50012, F50013, F50014, F50019 | 6 |
| F5002 | Anorexia nervosa, binge eating/purging type | 153 | FY2025 (Oct 1, 2024) | F50020, F50021, F50022, F50023, F50024, F50029 | 6 |
| F502 | Bulimia nervosa | 153 | FY2025 (Oct 1, 2024) | F5020, F5021, F5022, F5023, F5024, F5025 | 6 |
| G20 | Parkinson's disease | 199 | before FY2025 | G20A1, G20A2, G20B1, G20B2, G20C | 0 |
| G378 | Other specified demyelinating diseases of central nervous system | 198 | before FY2025 | G3781, G3789 | 0 |
| I248 | Other forms of acute ischemic heart disease | 229 | before FY2025 | I2481, I2489 | 0 |
| J156 | Pneumonia due to other Gram-negative bacteria | 282 | before FY2025 | J1561, J1569 | 0 |

A different case, for completeness: D71, E7253, G35 stopped being valid on Oct 1, 2025, but CMS 2026 still maps them, because 2026 payments use 2025 dates of service. The map is right to keep them.

## HCC numbers used by both V24 and V28

Same meaning is judged only from the map itself: `no` means no ICD-10-CM code maps to that number in both versions.

| HCC | V24 codes | V28 codes | Shared | Same meaning | V24 example | V28 example |
|---:|---:|---:|---:|---|---|---|
| 1 | 3 | 3 | 3 | yes | B20 Human immunodeficiency virus [HIV] disease | B20 Human immunodeficiency virus [HIV] disease |
| 2 | 53 | 52 | 51 | partly | A021 Salmonella sepsis | A021 Salmonella sepsis |
| 6 | 37 | 37 | 37 | yes | A072 Cryptosporidiosis | A072 Cryptosporidiosis |
| 17 | 23 | 75 | 0 | no | E0800 Diabetes mellitus due to underlying condition with hyperosmolarity without nonketotic hyperglycemic-hyperosmolar coma (NKHHC) | C771 Secondary and unspecified malignant neoplasm of intrathoracic lymph nodes |
| 18 | 400 | 26 | 0 | no | E0821 Diabetes mellitus due to underlying condition with diabetic nephropathy | C770 Secondary and unspecified malignant neoplasm of lymph nodes of head, face and neck |
| 19 | 6 | 63 | 0 | no | E089 Diabetes mellitus due to underlying condition without complications | C450 Mesothelioma of pleura |
| 21 | 11 | 434 | 0 | no | E40 Kwashiorkor | C01 Malignant neoplasm of base of tongue |
| 22 | 7 | 126 | 0 | no | E6601 Morbid (severe) obesity due to excess calories | C180 Malignant neoplasm of cecum |
| 23 | 240 | 231 | 0 | no | A391 Waterhouse-Friderichsen syndrome | C430 Malignant melanoma of lip |
| 35 | 77 | 1 | 0 | no | K5000 Crohn's disease of small intestine without complications | Z9483 Pancreas transplant status |
| 48 | 72 | 7 | 0 | no | C946 Myelodysplastic disease, not elsewhere classified | E6601 Morbid (severe) obesity due to excess calories |
| 51 | 67 | 11 | 0 | no | F01511 Vascular dementia, unspecified severity, with agitation | E220 Acromegaly and pituitary gigantism |
| 77 | 13 | 6 | 0 | no | G35 Multiple sclerosis | T86850 Intestine transplant rejection |
| 78 | 21 | 76 | 0 | no | G10 Huntington's disease | A5485 Gonococcal peritonitis |
| 79 | 58 | 2 | 0 | no | G40001 Localization-related (focal) (partial) idiopathic epilepsy and epileptic syndromes with seizures of localized onset, not intractable, with status epilepticus | K860 Alcohol-induced chronic pancreatitis |
| 80 | 51 | 28 | 0 | no | G931 Anoxic brain damage, not elsewhere classified | K5000 Crohn's disease of small intestine without complications |
| 107 | 141 | 14 | 0 | no | I2601 Septic pulmonary embolism with acute cor pulmonale | D5700 Hb-SS disease with crisis, unspecified |
| 108 | 327 | 39 | 0 | no | E0851 Diabetes mellitus due to underlying condition with diabetic peripheral angiopathy without gangrene | D561 Beta thalassemia |
| 111 | 17 | 2 | 0 | no | J410 Simple chronic bronchitis | D66 Hereditary factor VIII deficiency |
| 112 | 81 | 21 | 0 | no | B4481 Allergic bronchopulmonary aspergillosis | D6800 Von Willebrand disease, unspecified |
| 114 | 16 | 18 | 0 | no | A481 Legionnaires' disease | D810 Severe combined immunodeficiency [SCID] with reticular dysgenesis |
| 115 | 32 | 16 | 0 | no | A0103 Typhoid pneumonia | D700 Congenital agranulocytosis |
| 135 | 5 | 97 | 0 | no | N170 Acute kidney failure with tubular necrosis | F11150 Opioid abuse with opioid-induced psychotic disorder with delusions |
| 136 | 5 | 19 | 0 | no | I120 Hypertensive chronic kidney disease with stage 5 chronic kidney disease or end stage renal disease | F10131 Alcohol abuse with withdrawal delirium |
| 137 | 1 | 307 | 0 | no | N184 Chronic kidney disease, stage 4 (severe) | F11120 Opioid abuse with intoxication, uncomplicated |
| 138 | 3 | 14 | 0 | no | N1830 Chronic kidney disease, stage 3 unspecified | F1110 Opioid abuse, uncomplicated |

## Why it matters in 2026

CMS pays non-PACE Medicare Advantage on the 2024 CMS-HCC model (V28) at 100% in 2026. PACE blends 10% V28 with 90% V22, ESRD uses its own models, and Part D uses RxHCC V08. In the public code, Condition normalization adds HCC extensions from this map (`normalization/resources/condition.ts`), so a code that is not in the map gets no HCC extension, and anything built on that extension will not see it. An HCC number without a model label can point at two different condition groups.
