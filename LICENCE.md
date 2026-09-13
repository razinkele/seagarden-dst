# Licence

Copyright (c) 2026 Klaipėda University, Marine Research Institute, and the SeaGarden
project partners.

Licensed under the **European Union Public Licence v. 1.2 (EUPL-1.2)**.

You may not use this work except in compliance with the Licence. You may obtain a copy
of the Licence, in all official EU languages, at:

    https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12

Unless required by applicable law or agreed to in writing, software distributed under
the Licence is distributed on an **"AS IS" basis, WITHOUT WARRANTIES OR CONDITIONS OF
ANY KIND**, either express or implied. See the Licence for the specific language
governing permissions and limitations under the Licence.

> **Before first publication:** replace this file with the full verbatim EUPL-1.2 text
> from the URL above. A pointer is adequate for an internal draft; a redistributable
> release needs the text itself. Confirm the choice with KU legal — specification
> decision D8.

## Parameter files and data layers

The Application Form commits the project to open-access **source code and data
layers**. The parameter files under `params/` are released under the same licence as
the code.

Third-party data consumed by the tool (Copernicus Marine Service, EMODnet, HELCOM,
EEA) carries its own terms. Redistribution terms are recorded alongside each layer.
Any layer whose licence forbids redistribution is referenced by service call rather
than mirrored, and that dependency is logged as a durability risk — see specification
sections 6 and 14.

## Attribution of borrowed models

The growth formulation adapted in `growth.py` derives from OLAMUR (Horizon Europe
grant 101094065) deliverable D3.2. The shellfish yield model, elemental fractions and
salinity scaling derive from OLAMUR D2.3 and from:

> Maar, M. et al. (2023). Multi-use of offshore wind farms with low-trophic
> aquaculture can help achieve global sustainability goals. *Communications Earth &
> Environment*, 4, 447. https://doi.org/10.1038/s43247-023-01116-6

Cite these rather than this repository when the underlying science is what is being
referenced.
