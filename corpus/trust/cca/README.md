# CCA India root certificates

Source: https://cca.gov.in/root_certificate.html
Fetched: 2026-08-26

Root certificates of the **Controller of Certifying Authorities**, the Indian
government's root of trust for digital signatures under the IT Act 2000. Public
artefacts, intended for distribution.

Committed rather than fetched at runtime. A trust store downloaded at
verification time is a trust store an attacker on the network can influence.

| File | Subject | Key | Validity |
|---|---|---|---|
| CCAIndia2022.cer | CCA India 2022 | RSA-4096 | 2022-02-02 → 2042-02-02 |
| CCAIndia2022SPL.cer | CCA India 2022 SPL | RSA-4096 | 2022-09-20 → 2042-09-20 |
| CCAIndia2015.cer | CCA India 2015 SPL | RSA-2048 | |
| CCAIndia2014.cer | CCA India 2014 | RSA-2048 | |
| cca_india_2011.cer | CCA India 2011 | RSA-2048 | |
| cca_india_2007.cer | CCA India 2007 | RSA-2048 | 2007-06-13 → 2015-07-04 |
| cca_india.cer | CCA India | RSA-2048 | 2002-07-05 → 2009-07-04 |

CCA publishes some of these as DER and some as **bare base64 with no PEM
armour**. Bare base64 reaches a DER parser and parses *without error*, producing a
certificate with no subject and no key. `checker/trust.py` therefore refuses any
root that loads without a subject and a public key, rather than carrying it.

Expired roots are retained deliberately: a document signed in 2013 chains to a
root that has since expired, and validity is judged at **signing time**, not at
verification time.

## Not verified here

Revocation. No CRL or OCSP is fetched, so a chain that validates does not prove
the certificate was unrevoked. Intermediate CA certificates are also not held —
a document that does not embed its own issuer chain reports INCOMPLETE.
