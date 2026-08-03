{{
  config(
    materialized='table',
    tags=['intermediate', 'daily']
  )
}}

select
    orders.order_date,
    customers.customer_id
from {{ ref('sample_dbt_model_upstream') }} as orders
full join {{ source('raw_data', 'customers') }} as customers
on orders.order_date = customers.signup_date
