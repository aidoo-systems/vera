import "./globals.css";

export const metadata = {
  title: "VERA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="app-container">
        {children}
        <footer className="site-footer">
          <a href="https://www.aidoo.biz" target="_blank" rel="noopener">from ai.doo</a>
        </footer>
      </body>
    </html>
  );
}
