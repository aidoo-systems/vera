import "./globals.css";

export const metadata = {
  title: "VERA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="app-container">{children}</body>
    </html>
  );
}
