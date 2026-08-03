{{
  config(
    materialized='table'
  )
}}

select
    order_date,
    order_total
from {{ source('raw_data', 'orders') }}
