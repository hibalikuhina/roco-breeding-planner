# License for the offline Pokédex data

`pokedex.json` is an adapted dataset distributed under
[Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/legalcode.zh-Hans).

## Attribution

- Original community data: [洛克王国世界 WIKI](https://wiki.biligame.com/rocom/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4) and its contributors.
- Structured upstream source: [JayeGT002/rocom-wiki-data](https://github.com/JayeGT002/rocom-wiki-data), including its [license notice](https://github.com/JayeGT002/rocom-wiki-data/blob/main/LICENSE).
- Source file: [pets.json](https://jayegt002.github.io/rocom-wiki-data/data/pets.json), recorded at upstream commit `6ab264cb98eec1dd2dde0d7c6dfa200733a98d63`.

## Changes in this project

The upstream records were reduced to the fields needed by the breeding planner. Descriptions and image references were omitted. Egg-group numbers were mapped to Chinese names, and `family_base_id` was derived from the evolution relationship. See [`refresh_pokedex.py`](../refresh_pokedex.py) for the transformation and [`SOURCES.md`](../SOURCES.md) for source details.

Redistributions of this adapted dataset must preserve attribution, indicate changes, provide the CC BY-SA 4.0 license link, and follow its ShareAlike terms. This notice applies to `pokedex.json`; it does not grant a license for the application source code, personal data in `user_data/`, or third-party game artwork and trademarks.
