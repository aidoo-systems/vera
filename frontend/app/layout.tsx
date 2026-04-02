import "./globals.css";
import { AuthProvider } from "../components/AuthProvider";

export const metadata = {
  title: "VERA",
  description: "Verification-first OCR platform",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%234A90D9'/><text x='16' y='24' font-family='system-ui,sans-serif' font-size='22' font-weight='bold' fill='white' text-anchor='middle'>V</text></svg>",
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var s=localStorage.getItem('vera_theme');if(s==='dark'||(!s&&window.matchMedia('(prefers-color-scheme:dark)').matches)){document.documentElement.setAttribute('data-theme','dark')}})()`,
          }}
        />
      </head>
      <body className="app-container">
        <AuthProvider>
          {children}
        </AuthProvider>
        <footer className="site-footer">
          <a href="https://www.aidoo.biz" target="_blank" rel="noopener">from ai.doo</a>
        </footer>
      </body>
    </html>
  );
}
