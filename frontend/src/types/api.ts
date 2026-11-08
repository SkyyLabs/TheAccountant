export type Health = {
  status: "ok";
  version: string;
  schema_version: number;
};

export type ApiErrorBody = {
  error: { code: string; message: string };
};
