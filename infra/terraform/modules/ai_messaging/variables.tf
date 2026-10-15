variable "processing_queue_name" {
  description = "Nome da fila SQS standard que recebe tarefas de análise de imagens."
  type        = string
}

variable "dead_letter_queue_name" {
  description = "Nome da fila que recebe tarefas após esgotar as tentativas."
  type        = string
}

variable "max_receive_count" {
  description = "Número máximo de entregas da tarefa antes do redrive para a DLQ."
  type        = number
  default     = 3

  validation {
    condition     = var.max_receive_count >= 1
    error_message = "A fila precisa permitir ao menos uma entrega antes da DLQ."
  }
}

variable "visibility_timeout_seconds" {
  type        = number
  description = "Visibilidade da tarefa; staging usa o contrato de 180 segundos do worker."
  default     = 30
  validation {
    condition     = var.visibility_timeout_seconds >= 0 && var.visibility_timeout_seconds <= 43200 && floor(var.visibility_timeout_seconds) == var.visibility_timeout_seconds
    error_message = "Visibilidade deve ser um inteiro entre 0 e 43200 segundos."
  }
}

variable "receive_wait_time_seconds" {
  type    = number
  default = 0
  validation {
    condition     = var.receive_wait_time_seconds >= 0 && var.receive_wait_time_seconds <= 20 && floor(var.receive_wait_time_seconds) == var.receive_wait_time_seconds
    error_message = "Long polling deve ser um inteiro entre 0 e 20 segundos."
  }
}

variable "dead_letter_retention_seconds" {
  type    = number
  default = 345600
  validation {
    condition     = var.dead_letter_retention_seconds >= 60 && var.dead_letter_retention_seconds <= 1209600 && floor(var.dead_letter_retention_seconds) == var.dead_letter_retention_seconds
    error_message = "Retenção DLQ deve ser um inteiro entre 60 segundos e 14 dias."
  }
}
