import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout";

export default function NotFound() {
  return (
    <div className="mh-page">
      <PageHeader title="This page is not here" purpose="The link may be old, or there may be a typo. These pages are a good place to start." />
      <div className="mh-row mh-wrap">
        <Link to="/" className="mh-btn mh-btn-primary">Home</Link>
        <Link to="/check" className="mh-btn">Check a sentence</Link>
        <Link to="/judges" className="mh-btn">Judges start here</Link>
      </div>
    </div>
  );
}
