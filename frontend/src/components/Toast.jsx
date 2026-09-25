import { ToastCheck } from "../icons.jsx";

export default function Toast({ show, msg }) {
  return (
    <div className={"toast" + (show ? " show" : "")} id="toast" role="status">
      <ToastCheck />
      <span id="toastMsg">{msg}</span>
    </div>
  );
}
