# Third-party notices

ICD's own code and documentation are under the MIT License ([LICENSE](LICENSE)). This file lists material from other sources that ICD's repository contains or reproduces, with the notice each licence asks for.

Rules (competitor feature study, `docs/research/competitor-feature-study.md`, section 1):

- Code is copied only from MIT, Apache-2.0 or BSD sources, and each copy is listed here with its notice.
- Nothing is copied from GPL, AGPL, SSPL or Elastic License 2.0 sources (Wazuh, Kibana, Elastic detection rules, Security Onion). Ideas from them are re-implemented clean-room.
- Datasets are not covered by ICD's licence. Each keeps its own licence or terms, recorded in [docs/dataset-licence-register.md](docs/dataset-licence-register.md). No dataset row is committed to this repository.

Dependencies installed by `pip` and `npm` (`backend/requirements*.txt`, `frontend/package-lock.json`) are not vendored here; each ships its own licence.

## Entries

Each change that adds third-party material adds its entry below, in the same pull request.

### MITRE ATT&CK (tactic IDs and names)

- **What:** the 15 Enterprise ATT&CK tactic IDs and names in `backend/app/correlation/tactics.toml`, shown in an incident's key facts. No techniques, descriptions or other ATT&CK text are reproduced.
- **Source:** MITRE's STIX data `enterprise-attack.json` (matrix modified 2026-07-31), read from `wazuh/wazuh@6cc7b2e` `ruleset/mitre/`. Licence text from `mitre-attack/attack-stix-data` `LICENSE.txt` (read 25 Nov 2026), the same terms as https://attack.mitre.org/resources/legal-and-branding/terms-of-use/.
- **Licence (reproduced as the terms require):**

> **License**
>
> The MITRE Corporation (MITRE) hereby grants you a non-exclusive, royalty-free license to use ATT&CK® for research, development, and commercial purposes. Any copy you make for such purposes is authorized provided that you reproduce MITRE's copyright designation and this license in any such copy.
>
> "© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation."
>
> **Disclaimers**
>
> MITRE does not claim ATT&CK enumerates all possibilities for the types of actions and behaviors documented as part of its adversary model and framework of techniques. Using the information contained within ATT&CK to address or cover full categories of techniques will not guarantee full defensive coverage as there may be undisclosed techniques or variations on existing techniques not documented by ATT&CK.
>
> ALL DOCUMENTS AND THE INFORMATION CONTAINED THEREIN ARE PROVIDED ON AN "AS IS" BASIS AND THE CONTRIBUTOR, THE ORGANIZATION HE/SHE REPRESENTS OR IS SPONSORED BY (IF ANY), THE MITRE CORPORATION, ITS BOARD OF TRUSTEES, OFFICERS, AGENTS, AND EMPLOYEES, DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTY THAT THE USE OF THE INFORMATION THEREIN WILL NOT INFRINGE ANY RIGHTS OR ANY IMPLIED WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.

MITRE ATT&CK and ATT&CK are registered trademarks of The MITRE Corporation.

### Elastic Common Schema (field names)

- **What:** the 18 ECS field names in `backend/app/ingest/ecs_export.py` (`ECS_FIELDS`) used by the ECS export (`GET /uploads/{id}/ecs`). No ECS schema files, descriptions or code are reproduced; ICD's Event contract keeps its own names.
- **Source:** `elastic/ecs` tag `v9.5.0` (commit `401807e`), `generated/csv/fields.csv`, where each name was checked.
- **Licence:** Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0). The upstream NOTICE, reproduced as section 4(d) of the licence asks:

> Elastic Common Schema
> Copyright 2018-2021 Elasticsearch B.V.
>
> Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at
>
> http://www.apache.org/licenses/LICENSE-2.0
>
> Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
