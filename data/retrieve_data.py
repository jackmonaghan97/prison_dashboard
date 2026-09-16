
# import pandas as pd
import duckdb
import numpy as np
import pandas as pd
import warnings


# import datasets 
NUM_COLS = ['Person', 'Property', 'Public Order', 'Drug']

db_path = r"C:\Users\jackm\OneDrive\Documents\duckdb_cli-windows-amd64\my_database.duckdb"
con = duckdb.connect(db_path)

census_data = con.execute("SELECT * FROM illinois_demo").fetchdf()
prison_data = con.execute("SELECT * FROM prison_population_data_sets WHERE EXTRACT(MONTH FROM record_dt) = 12").fetchdf()

con.close()

# CENSUS CLEAN UP ----------------------------------------------

# remove duplicates from census data and unnecessary rows
where = census_data.duplicated()
census_data = census_data.loc[~where]


# set and combine age groups under 18
where = census_data['age'].isin(['<5', '5-9','10-14', '15-17'])
census_data.loc[where, 'age'] = '>18'

# set and combine age groups over 75
where = census_data['age'].isin(['75-84', '85<'])
census_data.loc[where, 'age'] = '75<'

census_data = census_data.loc[~census_data['year'].isna()]

where = (census_data['race'].str.contains('NATIVE'))
census_data.loc[where, 'race'] = 'American Indian'.upper()

where = (census_data['race'].str.contains('TWO'))
census_data.loc[where, 'race'] = 'Bi-Racial'.upper()

# EVENTUALLY I NEED TO CHECK WHY THIS IS
where = census_data['year'].isna()
census_data = census_data.loc[~where]

# UNFORTUNATELY I HAVE TO MERGE BECAUSE ^ THESE LINES CREATED DUPLICATES
id_cols = ['age', 'sex', 'race', 'year', 'county_name']
census_data['value'] = census_data['value'].astype(int)
census_merge = (
    census_data
    .groupby(by = id_cols)['value']
    .sum()
    .reset_index()
    .reindex()
)

where = census_merge['value'] < 10
census_merge = census_merge.loc[~where]

# PRISON CLEAN UP ----------------------------------------------

# grab top months only
current_month = prison_data['record_dt'].sort_values(ascending = False)[0].month
where = prison_data['record_dt'].dt.month == current_month
prison_data = prison_data.loc[where]
prison_data['stnccty'] = prison_data['stnccty'].str.lower() 

invalid_conditions = [
    prison_data['stnccty'].isin(['nan', 'Out of state']),
    prison_data['sex'].isin(['nan', 'B']),
    prison_data['race'].isin(['nan', 'Unknown', 'Not Assigned' , 'OTHER']),
    prison_data['birthdt'].isna()
]

where = pd.concat(invalid_conditions, axis=1).any(axis=1)
prison_data = prison_data.loc[~where]

# SORT AGE INTO BINS
prison_data['age'] = (prison_data['cstdt'] - prison_data['birthdt']).dt.days // 365
labels = ['>18', '18-19', '20-24', '25-29', '30-34', '35-44', 
          '45-54', '55-64', '65-74', '75<']
bins = [-np.inf, 18, 20, 25, 30, 35, 45, 55, 65, 75, np.inf]

# DEFINE BINS
prison_data['age_group'] = pd.cut(prison_data['age'], bins=bins,
                                 labels=labels, right=False)

# CRIME TYPE ---------------------------------------------

# take excel
url = 'idoc_public_map.xlsx'
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
mapping = pd.read_excel(url)
where = mapping['state_description'].duplicated()
mapping = mapping.loc[~where]
prison_data = prison_data.merge(
    mapping, 
    left_on = ['hofnscd'],
    right_on = 'state_description',
    how = 'left')

# GROUP DATA---------------------------------------------

# group
prison_data['year'] = prison_data['record_dt'].dt.year
grouped = (
    prison_data
    .groupby(
        by = ['sex', 'race', 'age_group', 'stnccty', 'crime_class', 'year'],
        observed = True)['docnbr']
    .count().reset_index()
    ).sort_values(by='docnbr', ascending=False)

# pivot
grouped = (grouped
    .pivot(
        index= ['sex', 'race', 'age_group', 'stnccty', 'year'],
        columns = 'crime_class', values='docnbr')
        .reset_index()
        )

grouped[NUM_COLS] = grouped[NUM_COLS].fillna(0)

# change 
upper_col = grouped[['sex', 'race']].apply(lambda col: col.str.upper())
grouped[['sex', 'race']] = upper_col

prison_data['key'] = prison_data['stnccty'].str.split(' ').str[0].str.lower()
prison_data[['sex', 'race']] = prison_data[['sex', 'race']].apply(lambda x: x.str.upper())
prison_data['race'] = prison_data['race'].str.replace('_OR_AFRICAN_AMERICAN', '')

census_merge['key'] = (census_merge['county_name']
        .str.split(' Cou').str[0]
        .str.replace('e W', 'ew')
        .str.lower())

census_merge['race'] = census_merge['race'].str.replace('_OR_AFRICAN_AMERICAN', '')
census_merge['race'] = census_merge['race'].str.replace('_OR_LATINO', '')
grouped['key'] = grouped['stnccty'].str.lower()
grouped['year_c'] = grouped['year'].clip(lower=2009, upper=2023)

result = census_merge.merge(grouped,
    left_on= ['age', 'sex', 'race', 'key', 'year'],
    right_on= ['age_group', 'sex', 'race', 'key', 'year_c'],
    how = 'left', suffixes = ['_cen', '_pri'])

# remove out of state
where = result['stnccty'] == 'out of state'
result = result.loc[~where]


# remove unnecessary columns, rename, and finally fillna
result.drop(columns = ['key', 'age_group', 'stnccty', 'year_c'], inplace = True)
result.rename(columns ={'value' : 'gen_population'}, inplace = True)
result[NUM_COLS] = result[NUM_COLS].fillna(0)
where = result['year_pri'].isna()
result.loc[where, 'year_pri'] = result.loc[where, 'year_cen']
result['total'] = result[NUM_COLS].sum(axis = 1)

result.to_csv('inc_data.csv', index=False)
