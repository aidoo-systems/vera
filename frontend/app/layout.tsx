import "./globals.css";
import { AuthProvider } from "../components/AuthProvider";

export const metadata = {
  title: "VERA",
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
