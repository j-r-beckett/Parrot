package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// SMSGatewayClient handles communication with SMS Gateway
type SMSGatewayClient struct {
	baseURL  string
	username string
	password string
	client   *http.Client
}

// Webhook represents a registered webhook
type Webhook struct {
	ID    string `json:"id"`
	URL   string `json:"url"`
	Event string `json:"event"`
}

// WebhookRegistration for registering new webhooks
type WebhookRegistration struct {
	URL   string `json:"url"`
	Event string `json:"event"`
}

// NewSMSGatewayClient creates a new SMS Gateway client
func NewSMSGatewayClient(baseURL, username, password string) *SMSGatewayClient {
	return &SMSGatewayClient{
		baseURL:  baseURL,
		username: username,
		password: password,
		client:   &http.Client{Timeout: 5 * time.Second},
	}
}

func (c *SMSGatewayClient) doRequest(method, path string, body interface{}) (*http.Response, error) {
	var reqBody io.Reader
	if body != nil {
		jsonBody, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reqBody = bytes.NewBuffer(jsonBody)
	}

	req, err := http.NewRequest(method, c.baseURL+path, reqBody)
	if err != nil {
		return nil, err
	}

	req.SetBasicAuth(c.username, c.password)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	return c.client.Do(req)
}

// GetWebhooks retrieves all registered webhooks
func (c *SMSGatewayClient) GetWebhooks() ([]Webhook, error) {
	resp, err := c.doRequest("GET", "/webhooks", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to get webhooks: status %d, body: %s", resp.StatusCode, body)
	}

	var webhooks []Webhook
	if err := json.NewDecoder(resp.Body).Decode(&webhooks); err != nil {
		return nil, err
	}

	return webhooks, nil
}

// DeleteWebhook deletes a webhook by ID
func (c *SMSGatewayClient) DeleteWebhook(id string) error {
	resp, err := c.doRequest("DELETE", "/webhooks/"+id, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to delete webhook: status %d, body: %s", resp.StatusCode, body)
	}

	return nil
}

// RegisterWebhook registers a new webhook for the given event
func (c *SMSGatewayClient) RegisterWebhook(event, callbackURL string) error {
	webhook := WebhookRegistration{
		URL:   callbackURL,
		Event: event,
	}

	resp, err := c.doRequest("POST", "/webhooks", webhook)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to register webhook: status %d, body: %s", resp.StatusCode, body)
	}

	return nil
}

// SendSMS sends an SMS message via SMS Gateway
func (c *SMSGatewayClient) SendSMS(phoneNumbers []string, message string, simNumber *int) (map[string]interface{}, error) {
	payload := map[string]interface{}{
		"phoneNumbers": phoneNumbers,
		"message":      message,
	}
	if simNumber != nil {
		payload["simNumber"] = *simNumber
	}

	resp, err := c.doRequest("POST", "/messages", payload)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode != http.StatusAccepted {
		return nil, fmt.Errorf("failed to send SMS: status %d, body: %s", resp.StatusCode, body)
	}

	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}

	return result, nil
}

// CheckHealth checks if the SMS Gateway is healthy and returns an error if not
func (c *SMSGatewayClient) CheckHealth() error {
	healthReq, err := http.NewRequest("GET", c.baseURL+"/health", nil)
	if err != nil {
		return err
	}
	healthReq.SetBasicAuth(c.username, c.password)

	resp, err := c.client.Do(healthReq)
	if err != nil {
		return fmt.Errorf("failed to connect to SMS Gateway: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("SMS Gateway health check returned status %d", resp.StatusCode)
	}

	return nil
}

// CheckSMSGatewayHealth checks if the SMS Gateway is healthy (legacy function for startup)
func CheckSMSGatewayHealth(url string) error {
	client := &http.Client{Timeout: 2 * time.Second}

	resp, err := client.Get(url + "/health")
	if err != nil {
		return fmt.Errorf("failed to connect to SMS Gateway: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("SMS Gateway health check returned status %d", resp.StatusCode)
	}

	return nil
}
