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
