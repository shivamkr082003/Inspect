import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("inspectai_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const getToken = () => localStorage.getItem("inspectai_token");

export const buildAuthedUrl = (path) => {
  const token = getToken();
  const sep = path.includes("?") ? "&" : "?";
  return `${API}${path}${sep}auth=${encodeURIComponent(token || "")}`;
};

export default api;
