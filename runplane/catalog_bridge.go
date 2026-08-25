package runplane

import "github.com/anvil008/swarm-coder/codingfleet"

func loadCatalogDocument() ([]string, error) {
	document, err := codingfleet.Load()
	if err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(document.Roles))
	for _, role := range document.Roles {
		ids = append(ids, role.ID)
	}
	return ids, nil
}
