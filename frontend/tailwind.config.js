/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pixiu: '#4D0099',
        'pixiu-dark': '#3b0075',
      }
    },
  },
  plugins: [],
  // 确保 Tailwind 在生产环境中也能正常工作
  important: false,
}
