# AIBox v5

## 還在因為 Alt Tab 而操勞嗎

每次跟 AI 對話，都要在瀏覽器、編輯器和 AI 工具之間不斷切換，按 Alt Tab 按到手指抽筋嗎？

AIBox v5 內建視窗置頂釘選功能，只要在界面上勾選置頂，視窗就會牢牢固定在螢幕最上層。你可以一邊看著你的程式碼編輯器，一邊直接在 AIBox 操作，完全不需要反覆切換視窗，大幅提升多文件智能開發的流暢度與效率。

## 解決 AI 對行號理解的痛點與節省上下文

通常 AI 在盲測或直接看程式碼時，根本無法主動精確理解錯誤到底發生在第幾行。

AIBox v5 完美解決了這個痛點。本工具在生成傳遞給 AI 的專案資料時，會自動為每一行程式碼精確標註行號[span_0](start_span)[span_0](end_span)。這樣一來，AI 就能清晰辨識完整的行號結構，並具備精確的行號定位與局部修改機制[span_1](start_span)[span_1](end_span)。

AI 不必完整輸出整份新版本檔案，距離上只需要針對需要變動的行號輸出局部程式碼[span_2](start_span)[span_2](end_span)，系統便會自動將變更精準應用到檔案中[span_3](start_span)[span_3](end_span)。這種設計不僅解決了 AI 找不到行號的盲區，更能大幅節省上下文與 Token 限制，在長程式碼的開發場景下優勢極為明顯。

## 專案核心功能
本工具的架構與完整邏輯請參考專案中的 hub.py[span_4](start_span)[span_4](end_span)。

- 強制路徑沙盒：AI 的任何文件操作皆無法跳出項目根目錄，防止誤刪或覆蓋專案外部檔案[span_5](start_span)[span_5](end_span)。
- 零風險執行隔離：預設在臨時沙盒副本中執行程式碼，完全不影響原始檔案，測試成功再應用[span_6](start_span)[span_6](end_span)。
- 專案依賴隔離：支援 Python 項目將套件自動安裝至專案內的獨立資料夾，不污染全域環境[span_7](start_span)[span_7](end_span)。
- 變更預覽與備份：提供清晰的檔案變更預覽，並支援一鍵備份專案[span_8](start_span)[span_8](end_span)。

## 下載與版本建議
本專案頁面同時提供完整原始碼與編譯完成的執行檔。請根據你的使用情境選擇最適合的下載版本：

- 走程式設計、有開發或客製化需求者：建議直接下載 aibox.py 原始碼，方便進行後續的二次開發或調校。
- 想直接使用、不想設定環境者：建議直接點擊下方連結下載編譯好的 aibox.exe 執行檔，下載後雙擊即可直接執行。

直接下載點：
- aibox.exe 執行檔直接下載：https://raw.githubusercontent.com/yang4271/aibox/main/aibox.exe
- hub.py 原始碼與核心邏輯下載：https://cdn.jsdelivr.net/gh/yang4271/aibox@main/hub.py

若你選擇透過 aibox.py 啟動，請執行以下指令：
python aibox.py -gui true

## 關於 hub.py
專案的核心邏輯皆編寫於 hub.py 中，包含文件節點管理、路徑安全攔截檢查、以及沙盒虛擬執行環境的建立[span_9](start_span)[span_9](end_span)。若需了解具體實現細節，請參閱 hub.py[span_10](start_span)[span_10](end_span)。

