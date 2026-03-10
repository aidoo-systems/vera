import Link from "next/link";

export default function NotFound() {
  return (
    <div className="error-page">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" width="64" height="64">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      <h1 className="error-title">404</h1>
      <p className="error-message">Page not found</p>
      <Link href="/" className="btn btn-primary">Back to home</Link>
    </div>
  );
}
