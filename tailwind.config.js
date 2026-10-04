module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        cream: "#FAF8F5",
        "surface-low": "#F4F3F0",
        paper: "#FFFFFF",
        graphite: "#22282F",
        "graphite-soft": "#4A525C",
        steelline: "#E4E1DA",
        // Тёмный янтарь из дизайн-системы Stitch: белый текст на нём даёт
        // контраст ≈6.5:1 (у прежнего #D97B1F было ≈3:1, ниже WCAG AA).
        amber: {
          DEFAULT: "#904D00",
          dark: "#6E3900",
          light: "#FE932C",
          tint: "#FFDCC3",
        },
        confirm: "#296F46",
        "confirm-bg": "#EAF4EE",
      },
      fontFamily: {
        sans: ["Manrope", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "16px",
      },
      maxWidth: {
        container: "1280px",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "sheet-up": {
          "0%": { opacity: "0", transform: "translateY(24px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "check-pop": {
          "0%": { opacity: "0", transform: "scale(0.6)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.5s ease-out both",
        "fade-in-up-fast": "fade-in-up 0.25s ease-out both",
        "sheet-up": "sheet-up 0.25s ease-out both",
        "check-pop": "check-pop 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};
