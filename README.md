# G.S.I. and Fundamental GeoPackage Builder

Grid Sheet Importer and Fundamental GeoPackage Builder is a QGIS plugin that fetches the Fundamental Geospatial Data (基盤地図情報) and the optimized vector tiles of the Geospatial Information Authority of Japan sheet by sheet (2nd-level meshes) and builds them into one GeoPackage, placed as grouped layers.

![QGIS](https://img.shields.io/badge/QGIS-3.44%2B%20%2F%204.x-green)
![Version](https://img.shields.io/badge/version-0.1.0-blue)

[日本語はこちら](#日本語)

---

## English

The Fundamental Geospatial Data is distributed as many ZIP files per mesh and per item, and has usually been converted into many shapefiles by hand. This plugin keeps it in a single GeoPackage instead: it fetches what the map view covers, remembers what is stored, and fetches again only what is missing or newer.

### Features

- **One GeoPackage**: the basic items of the Fundamental Geospatial Data and selected features of the optimized vector tiles are stored together in one file
- **Sheet by sheet**: the area is the 2nd-level meshes covering the map view, shown as orange frames on the map
- **Latest and stored status**: for each mesh and item, a table shows the latest data date on the service and what is already stored; data that is stored and up to date is not downloaded again
- **Stored areas on the map**: every stored mesh is coloured for the current selection of contents — green when all checked contents are stored, yellow when only some are (for example after checking a new item)
- **Safe stopping**: fetching goes mesh by mesh; *Stop* finishes the mesh being imported first, *Stop now* stops at once and leaves that mesh as it was — no half-imported mesh is left
- **Layer placement**: places the layers in a group in the Layers panel, either for the visible meshes only or for all stored areas
- **Preview map**: GSI Tiles (pale map) can be shown as a background while the window is open, to help choosing the area
- **English / Japanese** user interface, switched with a button

### Requirements

- QGIS 3.44 or later (QGIS 4.x supported)
- GDAL 3.8 or later (PMTiles driver, for the optimized vector tiles)
- An internet connection
- A free user account for the GSI download service (基盤地図情報ダウンロードサービス); fetching needs a login

### Installation

#### From ZIP

1. Download the ZIP file of a release
2. In QGIS, open *Plugins → Manage and Install Plugins… → Install from ZIP*
3. Select the ZIP file and install

The plugin appears in the *Web* menu and on the *Web* toolbar.

### Basic workflow

1. Open the plugin from the *Web* menu
2. Move the map to the area you need; the meshes covering the view are shown with orange frames
3. Check the items you need under "Data to use" on the left
4. Choose the GeoPackage to save to and the group name
5. Press *Fetch* (log in when asked)
6. The layers are placed in the Layers panel when fetching has finished

### Notes

- The optimized vector tiles are a trial release by GSI; the URL and the contents may change. They can also be obtained separately from the [GSI release page](https://github.com/gsi-cyberjapan/optimal_bvmap)
- The login ID and password can be saved in the QGIS settings for automatic filling; they are **not encrypted**, so this is not recommended on a shared PC
- Japan only

### Disclaimer

- This plugin was **not made by the Geospatial Information Authority of Japan (GSI)**, and is not endorsed or guaranteed by GSI
- Use of the fetched data must follow the [GSI terms of use](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html) and the Survey Act of Japan: show the source, note any processing, and apply for approval where required. Whether an application is required can be checked with GSI's *地図の利用手続ナビ*
- The plugin is provided without warranty; the author takes no responsibility for any result of its use

### License

GNU General Public License v2 or later. See [LICENSE](LICENSE).

### Author

Hideharu Masai

---

## 日本語

Grid Sheet Importer and Fundamental GeoPackage Builder は国土地理院の基盤地図情報と最適化ベクトルタイルを、見ている地図の範囲だけ取得し、1つの GeoPackage にまとめる QGIS プラグインです。

基盤地図情報は、メッシュごと・項目ごとの多数の ZIP で配られ、これまでは手作業で多数のシェープファイルに変換することが多かったものです。このプラグインは、それを1つの GeoPackage にまとめて持ちます。表示範囲の分を取得し、保存したものを覚えておき、足りないものと新しくなったものだけを取り直します。

### 主な機能

- **1つの GeoPackage**：基盤地図情報の基本項目と、最適化ベクトルタイルの選んだ地物を、1つのファイルにまとめて保存
- **図郭ごと**：範囲は表示範囲に掛かる2次メッシュ。地図に橙の枠で示す
- **最新と保存済みの状況**：メッシュ・項目ごとに、サービス上の最新データの日付と保存済みの状況を表で示す。保存済みで最新のものは取り直さない
- **取得済みの範囲を地図に**：保存済みのメッシュを、今のチェックに対して塗り分ける。チェックした内容がそろっていれば緑、一部だけなら黄（項目を足したときなど）
- **安全な中止**：取得はメッシュごとに進む。「中止」は取り込み中のメッシュを終えてから止まり、「すぐに止める」はそのメッシュを取得前の状態のまま止まる。中途半端に取り込まれたメッシュは残らない
- **レイヤーへの配置**：レイヤーパネルのグループに置く。可視範囲のメッシュだけか、取得済みの範囲すべてかを選べる
- **プレビュー地図**：窓を開いている間、地理院タイル（淡色地図）を背景に出せる。範囲を選ぶときの目安に
- **英語／日本語**の画面。ボタンで切り替え

### 動作環境

- QGIS 3.44 以降（QGIS 4.x に対応）
- GDAL 3.8 以降（最適化ベクトルタイルに PMTiles ドライバーを使う）
- インターネット接続
- 基盤地図情報ダウンロードサービスの利用者登録（無料）。取得にはログインが必要

### インストール

#### ZIP から

1. リリースの ZIP ファイルをダウンロード
2. QGIS で「プラグイン → プラグインの管理とインストール… → ZIP からインストール」を開く
3. ZIP ファイルを選んでインストール

プラグインは「Web」メニューと「Web」ツールバーに入ります。

### 基本の流れ

1. 「Web」メニューからプラグインを開く
2. 必要な場所へ地図を動かす。表示範囲に掛かるメッシュが橙の枠で出る
3. 左の「使用データ」で、必要な項目にチェックを入れる
4. 保存先の GeoPackage とグループ名を決める
5. 「取得」を押す（求められたらログインする）
6. 取得が終わると、レイヤーパネルに配置される

### 注意

- 最適化ベクトルタイルは国土地理院の試験公開です。URL やデータの内容が変わることがあります。[国土地理院の公開ページ](https://github.com/gsi-cyberjapan/optimal_bvmap)から別途取得することもできます
- ログインID・パスワードは、自動入力のために QGIS の設定に保存できます。**暗号化されない**ので、共有PCでは推奨しません
- 日本国内のみ

### 免責事項

- このプラグインは**国土地理院が制作したものではありません**。国土地理院が推奨・保証するものでもありません
- 取得したデータの利用は、[国土地理院の利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)と測量法に従ってください（出典の明示、加工した旨の記載、場合によっては承認申請）。申請が要るかどうかは、国土地理院の「地図の利用手続ナビ」で確認できます
- このプラグインは無保証です。使用によって生じた結果について、作者は責任を負いません

### ライセンス

GNU General Public License v2 以降。[LICENSE](LICENSE) をご覧ください。

### 作者

Hideharu Masai
