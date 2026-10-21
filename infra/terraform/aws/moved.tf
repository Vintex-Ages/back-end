# Address compatibility only; separate legacy states require reviewed migration.
moved {
  from = module.network
  to   = module.network[0]
}
moved {
  from = module.registry
  to   = module.registry[0]
}
moved {
  from = module.budget
  to   = module.budget[0]
}
moved {
  from = module.services
  to   = module.services[0]
}
moved {
  from = module.host
  to   = module.host[0]
}
moved {
  from = module.scheduler
  to   = module.scheduler[0]
}
