/** @type {import('tailwindcss').Config} */
export default {
  // i18n 資源檔排除在外（ADR-032）：那些檔案只有譯文字串、不含任何 class name，
  // 但 JIT 的 content 掃描是純 token 比對——英文譯文裡剛好等於某個 utility 名稱的
  // 單字（如「WI outline」的 outline）會被當成候選 class，產出沒有任何元素在用的
  // 死規則。掃描它們只有偽陽性，沒有真陽性。
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    '!./src/shared/i18n/resources/**',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
