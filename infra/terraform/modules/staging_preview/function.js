// Bloqueia o cadastro público na borda. As contas de demo são criadas dentro
// da instância, sem passar pelo CloudFront.
function handler(event) {
  var request = event.request;
  var path = request.uri;
  try {
    path = decodeURIComponent(path);
  } catch (error) {
    return request;
  }
  path = path.replace(/\/{2,}/g, '/').replace(/\/+$/, '').toLowerCase();
  if (request.method === 'POST' && path === '/api/auth/register') {
    return {
      statusCode: 403,
      statusDescription: 'Forbidden',
      headers: { 'content-type': { value: 'application/json' } },
      body: '{"error":{"code":"REGISTRATION_CLOSED","message":"Cadastro fechado nesta staging."}}'
    };
  }
  return request;
}
