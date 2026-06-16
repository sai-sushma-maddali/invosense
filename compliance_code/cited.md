<!-- Malaysia GST/SST tax rules used by InvoSense compliance checks -->
<!-- Canonical reference for check_tax_rate -->

# Malaysia Tax Rules (GST / SST)

Effective rates applied by invoice date:

| effective_from | effective_to | rate | description |
| --- | --- | --- | --- |
| 2015-04-01 | 2018-05-31 | 0.06 | Malaysia GST 6% |
| 2018-06-01 | 2018-08-31 | 0.00 | Zero-rated transition period (tax holiday) |
| 2018-09-01 | | 0.06 | Malaysia SST 6% service / 10% sales |

```json
{
  "tax_rules": [
    {"valid_from": "2015-04-01", "valid_to": "2018-05-31", "rate": 0.06},
    {"valid_from": "2018-06-01", "valid_to": "2018-08-31", "rate": 0.0},
    {"valid_from": "2018-09-01", "valid_to": null, "rate": 0.06}
  ]
}
```
